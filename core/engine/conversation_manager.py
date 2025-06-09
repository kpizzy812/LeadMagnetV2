# core/engine/conversation_manager.py

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import (
    Conversation, Message, Lead, Session, ConversationStatus,
    FunnelStage, MessageRole, FollowupSchedule
)
from personas.persona_factory import create_persona_for_session, PersonaRole
from core.integrations.openai_client import OpenAIClient
from workflows.followups.scheduler import followup_scheduler
from loguru import logger


class ConversationManager:
    """Менеджер диалогов - центральный компонент для работы с беседами"""

    def __init__(self):
        self.openai_client = OpenAIClient()
        self._active_conversations: Dict[int, Conversation] = {}

    async def get_conversation(
            self,
            lead_username: str,
            session_name: str,
            create_if_not_exists: bool = True
    ) -> Optional[Conversation]:
        """Получение или создание диалога"""

        async with get_db() as db:
            # Поиск существующего диалога
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .options(selectinload(Conversation.messages))
                .join(Lead)
                .join(Session)
                .where(Lead.username == lead_username)
                .where(Session.session_name == session_name)
            )
            conversation = result.scalar_one_or_none()

            if conversation:
                self._active_conversations[conversation.id] = conversation
                return conversation

            if not create_if_not_exists:
                return None

            # Создание нового диалога
            lead = await self._get_or_create_lead(db, lead_username)
            session = await self._get_or_create_session(db, session_name)

            conversation = Conversation(
                lead_id=lead.id,
                session_id=session.id,
                status=ConversationStatus.ACTIVE,
                current_stage=FunnelStage.INITIAL_CONTACT
            )

            db.add(conversation)
            await db.flush()
            await db.refresh(conversation)

            # Загружаем связанные объекты
            await db.refresh(conversation, ['lead', 'session'])

            self._active_conversations[conversation.id] = conversation

            logger.info(f"🆕 Создан новый диалог: {lead_username} ↔ {session_name}")
            return conversation

    async def process_user_message(
            self,
            conversation_id: int,
            message_text: str,
            telegram_message_id: Optional[int] = None
    ) -> Optional[str]:
        """Обработка сообщения от пользователя"""

        try:
            async with get_db() as db:
                # Загружаем диалог с зависимостями
                result = await db.execute(
                    select(Conversation)
                    .options(selectinload(Conversation.lead))
                    .options(selectinload(Conversation.session))
                    .options(selectinload(Conversation.messages))
                    .where(Conversation.id == conversation_id)
                )
                conversation = result.scalar_one_or_none()

                if not conversation:
                    logger.error(f"❌ Диалог {conversation_id} не найден")
                    return None

                if conversation.status != ConversationStatus.ACTIVE:
                    logger.warning(f"⚠️ Диалог {conversation_id} неактивен: {conversation.status}")
                    return None

                # Сохраняем сообщение пользователя
                user_message = Message(
                    conversation_id=conversation.id,
                    lead_id=conversation.lead_id,
                    session_id=conversation.session_id,
                    role=MessageRole.USER,
                    content=message_text,
                    requires_response=True
                )
                db.add(user_message)

                # Обновляем статистику диалога
                conversation.messages_count += 1
                conversation.user_messages_count += 1
                conversation.last_user_message_at = datetime.utcnow()

                await db.flush()

                # Генерируем ответ
                response_text = await self._generate_response(conversation, message_text)

                if response_text:
                    # Сохраняем ответ
                    assistant_message = Message(
                        conversation_id=conversation.id,
                        lead_id=conversation.lead_id,
                        session_id=conversation.session_id,
                        role=MessageRole.ASSISTANT,
                        content=response_text,
                        funnel_stage=conversation.current_stage,
                        processed=True
                    )
                    db.add(assistant_message)

                    # Обновляем статистику
                    conversation.messages_count += 1
                    conversation.assistant_messages_count += 1
                    conversation.last_assistant_message_at = datetime.utcnow()

                    # Помечаем пользовательское сообщение как обработанное
                    user_message.processed = True
                    user_message.requires_response = False

                    await db.commit()

                    logger.info(f"✅ Ответ сгенерирован для диалога {conversation_id}")
                    # Планируем фолоуап при необходимости
                    await self._schedule_followup_if_needed(conversation)

                    return response_text

                await db.commit()
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения в диалоге {conversation_id}: {e}")
            return None


    async def _generate_response(self, conversation: Conversation, user_message: str) -> Optional[str]:
        """Генерация ответа с помощью ИИ"""

        try:
            # Создаем персону для сессии
            session = conversation.session
            if not session.persona_type:
                logger.error(f"❌ У сессии {session.session_name} не указан тип персоны")
                return None

            persona = create_persona_for_session(
                session_name=session.session_name,
                persona_type=PersonaRole(session.persona_type),
                ref_link=session.project_ref_link or "",
                project_id="default"  # TODO: сделать настраиваемым
            )

            # Анализируем сообщение пользователя
            conversation_history = [
                {"role": msg.role, "content": msg.content}
                for msg in conversation.messages[-10:]  # Последние 10 сообщений
            ]

            analysis = persona.analyze_user_message(user_message, conversation_history)

            # Возможно обновляем этап воронки
            new_stage = await self._determine_funnel_stage(conversation, user_message, analysis)
            if new_stage != conversation.current_stage:
                conversation.current_stage = new_stage
                logger.info(f"🔄 Диалог {conversation.id} перешел на этап: {new_stage}")

            # Формируем контекст для ИИ
            context = {
                "conversation_id": conversation.id,
                "current_stage": conversation.current_stage,
                "lead_username": conversation.lead.username,
                "ref_link_sent": conversation.ref_link_sent,
                "messages_count": conversation.messages_count,
                "analysis": analysis
            }

            # Получаем промпты от персоны
            system_prompt = persona.get_system_prompt(context)
            stage_instruction = persona.get_funnel_stage_instruction(conversation.current_stage, context)

            # Формируем историю сообщений для ИИ
            messages = []

            # Системный промпт
            messages.append({
                "role": "system",
                "content": f"{system_prompt}\n\nИНСТРУКЦИЯ ДЛЯ ТЕКУЩЕГО ЭТАПА:\n{stage_instruction}"
            })

            # История диалога
            for msg in conversation.messages[-8:]:  # Последние 8 сообщений для контекста
                messages.append({
                    "role": "user" if msg.role == MessageRole.USER else "assistant",
                    "content": msg.content
                })

            # Текущее сообщение пользователя
            messages.append({
                "role": "user",
                "content": user_message
            })

            # Генерируем ответ через OpenAI
            response = await self.openai_client.generate_response(messages)

            # Проверяем отправку реф ссылки
            if not conversation.ref_link_sent and session.project_ref_link:
                if session.project_ref_link in response:
                    conversation.ref_link_sent = True
                    conversation.ref_link_sent_at = datetime.utcnow()
                    logger.info(f"🔗 Реф ссылка отправлена в диалоге {conversation.id}")

            return response

        except Exception as e:
            logger.error(f"❌ Ошибка генерации ответа: {e}")
            return None

    async def _determine_funnel_stage(
            self,
            conversation: Conversation,
            user_message: str,
            analysis: Dict[str, Any]
    ) -> FunnelStage:
        """Определение этапа воронки на основе анализа"""

        current_stage = FunnelStage(conversation.current_stage)
        message_lower = user_message.lower()

        # Логика определения следующего этапа
        if current_stage == FunnelStage.INITIAL_CONTACT:
            if analysis.get("interest_level") == "high":
                return FunnelStage.TRUST_BUILDING
            elif any(word in message_lower for word in ["проект", "инвест", "заработок"]):
                return FunnelStage.PROJECT_INQUIRY

        elif current_stage == FunnelStage.TRUST_BUILDING:
            if analysis.get("project_mentions"):
                return FunnelStage.PROJECT_INQUIRY
            elif analysis.get("interest_level") == "high":
                return FunnelStage.INTEREST_QUALIFICATION

        elif current_stage == FunnelStage.PROJECT_INQUIRY:
            if analysis.get("interest_level") == "high":
                return FunnelStage.INTEREST_QUALIFICATION

        elif current_stage == FunnelStage.INTEREST_QUALIFICATION:
            if analysis.get("interest_level") == "high" and not conversation.ref_link_sent:
                return FunnelStage.PRESENTATION

        elif current_stage == FunnelStage.PRESENTATION:
            if analysis.get("objections"):
                return FunnelStage.OBJECTION_HANDLING
            elif analysis.get("interest_level") == "high":
                return FunnelStage.CONVERSION

        elif current_stage == FunnelStage.OBJECTION_HANDLING:
            if analysis.get("sentiment") == "positive":
                return FunnelStage.CONVERSION

        elif current_stage == FunnelStage.CONVERSION:
            if conversation.ref_link_sent and analysis.get("sentiment") == "positive":
                return FunnelStage.POST_CONVERSION

        return current_stage

    async def _get_or_create_lead(self, db, username: str) -> Lead:
        """Получение или создание лида"""
        result = await db.execute(select(Lead).where(Lead.username == username))
        lead = result.scalar_one_or_none()

        if not lead:
            lead = Lead(username=username)
            db.add(lead)
            await db.flush()
            await db.refresh(lead)

        return lead

    async def _get_or_create_session(self, db, session_name: str) -> Session:
        """Получение или создание сессии"""
        result = await db.execute(select(Session).where(Session.session_name == session_name))
        session = result.scalar_one_or_none()

        if not session:
            session = Session(
                session_name=session_name,
                persona_type=PersonaRole.BASIC_MAN  # По умолчанию
            )
            db.add(session)
            await db.flush()
            await db.refresh(session)

        return session

    async def get_conversations_needing_response(self) -> List[Conversation]:
        """Получение диалогов, требующих ответа"""
        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .options(selectinload(Conversation.messages))
                .join(Message)
                .where(Message.requires_response == True)
                .where(Message.processed == False)
                .where(Conversation.status == ConversationStatus.ACTIVE)
            )
            return result.scalars().unique().all()

    async def schedule_followup(
            self,
            conversation_id: int,
            followup_type: str,
            delay_hours: int = 24
    ):
        """Планирование фолоуап сообщения"""
        async with get_db() as db:
            scheduled_at = datetime.utcnow() + timedelta(hours=delay_hours)

            followup = FollowupSchedule(
                conversation_id=conversation_id,
                followup_type=followup_type,
                scheduled_at=scheduled_at
            )

            db.add(followup)
            await db.commit()

            logger.info(f"📅 Запланирован фолоуап {followup_type} для диалога {conversation_id} на {scheduled_at}")

    async def _schedule_followup_if_needed(self, conversation: Conversation):
        """Планирование фолоуапа при необходимости"""

        try:
            # Если реф ссылка уже отправлена - фолоуапы не нужны
            if conversation.ref_link_sent:
                return

            # Проверяем этап воронки - фолоуапы нужны только после определенных этапов
            stages_needing_followup = [
                FunnelStage.TRUST_BUILDING,
                FunnelStage.PROJECT_INQUIRY,
                FunnelStage.INTEREST_QUALIFICATION,
                FunnelStage.PRESENTATION
            ]

            if conversation.current_stage not in stages_needing_followup:
                return

            # Планируем напоминание через 6 часов если пользователь не ответит
            await followup_scheduler.schedule_followup_for_inactive_conversation(
                conversation.id
            )

            logger.info(f"📅 Запланирован фолоуап для диалога {conversation.id}")

        except Exception as e:
            logger.error(f"❌ Ошибка планирования фолоуапа: {e}")


# Глобальный экземпляр менеджера диалогов
conversation_manager = ConversationManager()