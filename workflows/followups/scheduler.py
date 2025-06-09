# workflows/followups/scheduler.py

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import (
    FollowupSchedule, Conversation, Lead, Session, ConversationStatus
)
from personas.persona_factory import create_persona_for_session, PersonaRole
from core.integrations.telegram_client import telegram_session_manager
from loguru import logger


class FollowupScheduler:
    """Планировщик фолоуап сообщений"""

    def __init__(self):
        self.running = False
        self.check_interval = 60  # Проверка каждые 60 секунд

    async def start(self):
        """Запуск планировщика"""
        self.running = True
        logger.info("🚀 Запуск планировщика фолоуапов")

        while self.running:
            try:
                await self._process_scheduled_followups()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике фолоуапов: {e}")
                await asyncio.sleep(10)

    async def stop(self):
        """Остановка планировщика"""
        self.running = False
        logger.info("🛑 Планировщик фолоуапов остановлен")

    async def schedule_followup(
            self,
            conversation_id: int,
            followup_type: str,
            delay_hours: int = 24,
            custom_message: Optional[str] = None
    ) -> bool:
        """Планирование фолоуап сообщения"""

        try:
            async with get_db() as db:
                # Проверяем что диалог существует
                conv_result = await db.execute(
                    select(Conversation)
                    .options(selectinload(Conversation.lead))
                    .options(selectinload(Conversation.session))
                    .where(Conversation.id == conversation_id)
                )
                conversation = conv_result.scalar_one_or_none()

                if not conversation:
                    logger.error(f"❌ Диалог {conversation_id} не найден")
                    return False

                # Проверяем что уже нет запланированного фолоуапа этого типа
                existing_result = await db.execute(
                    select(FollowupSchedule)
                    .where(
                        FollowupSchedule.conversation_id == conversation_id,
                        FollowupSchedule.followup_type == followup_type,
                        FollowupSchedule.executed == False
                    )
                )
                existing = existing_result.scalar_one_or_none()

                if existing:
                    logger.warning(f"⚠️ Фолоуап {followup_type} уже запланирован для диалога {conversation_id}")
                    return False

                # Создаем новый фолоуап
                scheduled_at = datetime.utcnow() + timedelta(hours=delay_hours)

                followup = FollowupSchedule(
                    conversation_id=conversation_id,
                    followup_type=followup_type,
                    scheduled_at=scheduled_at,
                    message_template=custom_message
                )

                db.add(followup)
                await db.commit()

                logger.info(
                    f"📅 Запланирован фолоуап {followup_type} для диалога {conversation_id} "
                    f"на {scheduled_at.strftime('%d.%m.%Y %H:%M')}"
                )

                return True

        except Exception as e:
            logger.error(f"❌ Ошибка планирования фолоуапа: {e}")
            return False

    async def _process_scheduled_followups(self):
        """Обработка запланированных фолоуапов"""

        try:
            async with get_db() as db:
                # Находим готовые к выполнению фолоуапы
                now = datetime.utcnow()

                result = await db.execute(
                    select(FollowupSchedule)
                    .options(selectinload(FollowupSchedule.conversation))
                    .options(selectinload(FollowupSchedule.conversation, Conversation.lead))
                    .options(selectinload(FollowupSchedule.conversation, Conversation.session))
                    .where(
                        FollowupSchedule.executed == False,
                        FollowupSchedule.scheduled_at <= now
                    )
                    .order_by(FollowupSchedule.scheduled_at)
                    .limit(10)  # Обрабатываем не более 10 за раз
                )

                followups = result.scalars().all()

                if not followups:
                    return

                logger.info(f"📬 Обрабатываем {len(followups)} фолоуапов")

                for followup in followups:
                    await self._execute_followup(followup)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки фолоуапов: {e}")

    async def _execute_followup(self, followup: FollowupSchedule):
        """Выполнение конкретного фолоуапа"""

        try:
            conversation = followup.conversation

            # Проверяем что диалог еще активен
            if conversation.status != ConversationStatus.ACTIVE:
                logger.info(f"⏭️ Пропускаем фолоуап для неактивного диалога {conversation.id}")
                await self._mark_followup_executed(followup.id, "Диалог неактивен")
                return

            # Генерируем сообщение
            message_text = await self._generate_followup_message(followup, conversation)

            if not message_text:
                logger.error(f"❌ Не удалось сгенерировать сообщение для фолоуапа {followup.id}")
                return

            # Отправляем сообщение
            success = await telegram_session_manager.send_message(
                session_name=conversation.session.session_name,
                username=conversation.lead.username,
                message=message_text
            )

            if success:
                # Сохраняем сообщение в БД
                await self._save_followup_message(conversation, message_text, followup.followup_type)

                # Помечаем фолоуап как выполненный
                await self._mark_followup_executed(followup.id, message_text)

                logger.success(
                    f"✅ Фолоуап {followup.followup_type} отправлен: "
                    f"{conversation.session.session_name} → {conversation.lead.username}"
                )

                # Планируем следующий фолоуап если нужно
                await self._schedule_next_followup(conversation, followup.followup_type)

            else:
                logger.error(f"❌ Не удалось отправить фолоуап {followup.id}")

        except Exception as e:
            logger.error(f"❌ Ошибка выполнения фолоуапа {followup.id}: {e}")

    async def _generate_followup_message(
            self,
            followup: FollowupSchedule,
            conversation: Conversation
    ) -> Optional[str]:
        """Генерация текста фолоуап сообщения"""

        try:
            # Если есть кастомный шаблон - используем его
            if followup.message_template:
                return followup.message_template

            # Создаем персону для генерации сообщения
            session = conversation.session
            if not session.persona_type:
                logger.error(f"❌ У сессии {session.session_name} не указан тип персоны")
                return None

            persona = create_persona_for_session(
                session_name=session.session_name,
                persona_type=PersonaRole(session.persona_type),
                ref_link=session.project_ref_link or "",
                project_id="default"
            )

            # Формируем контекст
            context = {
                "conversation_id": conversation.id,
                "lead_username": conversation.lead.username,
                "current_stage": conversation.current_stage,
                "ref_link_sent": conversation.ref_link_sent,
                "messages_count": conversation.messages_count,
                "last_message_time": conversation.last_user_message_at
            }

            # Получаем шаблон от персоны
            message_text = persona.get_followup_message_template(followup.followup_type, context)

            return message_text

        except Exception as e:
            logger.error(f"❌ Ошибка генерации фолоуап сообщения: {e}")
            return None

    async def _save_followup_message(
            self,
            conversation: Conversation,
            message_text: str,
            followup_type: str
    ):
        """Сохранение фолоуап сообщения в БД"""

        try:
            from storage.models.base import Message, MessageRole

            async with get_db() as db:
                message = Message(
                    conversation_id=conversation.id,
                    lead_id=conversation.lead_id,
                    session_id=conversation.session_id,
                    role=MessageRole.ASSISTANT,
                    content=message_text,
                    funnel_stage=conversation.current_stage,
                    is_followup=True,
                    processed=True
                )

                db.add(message)

                # Обновляем статистику диалога
                conversation.messages_count += 1
                conversation.assistant_messages_count += 1
                conversation.last_assistant_message_at = datetime.utcnow()

                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения фолоуап сообщения: {e}")

    async def _mark_followup_executed(self, followup_id: int, generated_message: str):
        """Отметка фолоуапа как выполненного"""

        try:
            async with get_db() as db:
                await db.execute(
                    update(FollowupSchedule)
                    .where(FollowupSchedule.id == followup_id)
                    .values(
                        executed=True,
                        executed_at=datetime.utcnow(),
                        generated_message=generated_message
                    )
                )
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка отметки фолоуапа как выполненного: {e}")

    async def _schedule_next_followup(self, conversation: Conversation, current_type: str):
        """Планирование следующего фолоуапа"""

        # Логика последовательности фолоуапов
        followup_sequence = {
            "reminder": ("value", 48),  # Через 2 дня -> ценность
            "value": ("proof", 72),  # Через 3 дня -> доказательство
            "proof": ("final", 96),  # Через 4 дня -> финальный
            "final": None  # Последний
        }

        next_followup = followup_sequence.get(current_type)

        if next_followup and not conversation.ref_link_sent:
            next_type, delay_hours = next_followup

            await self.schedule_followup(
                conversation_id=conversation.id,
                followup_type=next_type,
                delay_hours=delay_hours
            )

    async def schedule_followup_for_inactive_conversation(self, conversation_id: int):
        """Планирование фолоуапа для неактивного диалога"""

        try:
            async with get_db() as db:
                # Проверяем когда было последнее сообщение от пользователя
                conv_result = await db.execute(
                    select(Conversation)
                    .where(Conversation.id == conversation_id)
                )
                conversation = conv_result.scalar_one_or_none()

                if not conversation:
                    return

                # Если пользователь не отвечал больше 4 часов - планируем напоминание
                if conversation.last_user_message_at:
                    time_since_last = datetime.utcnow() - conversation.last_user_message_at

                    if time_since_last > timedelta(hours=4):
                        # Проверяем что еще нет запланированного фолоуапа
                        existing_result = await db.execute(
                            select(FollowupSchedule)
                            .where(
                                FollowupSchedule.conversation_id == conversation_id,
                                FollowupSchedule.executed == False
                            )
                        )
                        existing = existing_result.scalar_one_or_none()

                        if not existing:
                            await self.schedule_followup(
                                conversation_id=conversation_id,
                                followup_type="reminder",
                                delay_hours=4  # Через 4 часа
                            )

        except Exception as e:
            logger.error(f"❌ Ошибка планирования фолоуапа для неактивного диалога: {e}")

    async def get_pending_followups(self) -> List[Dict[str, Any]]:
        """Получение списка ожидающих фолоуапов"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(FollowupSchedule)
                    .options(selectinload(FollowupSchedule.conversation))
                    .options(selectinload(FollowupSchedule.conversation, Conversation.lead))
                    .options(selectinload(FollowupSchedule.conversation, Conversation.session))
                    .where(FollowupSchedule.executed == False)
                    .order_by(FollowupSchedule.scheduled_at)
                )

                followups = result.scalars().all()

                result_list = []
                for followup in followups:
                    result_list.append({
                        "id": followup.id,
                        "type": followup.followup_type,
                        "scheduled_at": followup.scheduled_at,
                        "conversation_id": followup.conversation_id,
                        "lead_username": followup.conversation.lead.username,
                        "session_name": followup.conversation.session.session_name,
                        "time_left": (followup.scheduled_at - datetime.utcnow()).total_seconds()
                    })

                return result_list

        except Exception as e:
            logger.error(f"❌ Ошибка получения ожидающих фолоуапов: {e}")
            return []

    async def cancel_followup(self, followup_id: int) -> bool:
        """Отмена фолоуапа"""

        try:
            async with get_db() as db:
                await db.execute(
                    update(FollowupSchedule)
                    .where(FollowupSchedule.id == followup_id)
                    .values(
                        executed=True,
                        executed_at=datetime.utcnow(),
                        generated_message="Отменено администратором"
                    )
                )
                await db.commit()

                logger.info(f"🗑️ Фолоуап {followup_id} отменен")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка отмены фолоуапа: {e}")
            return False


# Глобальный экземпляр планировщика
followup_scheduler = FollowupScheduler()