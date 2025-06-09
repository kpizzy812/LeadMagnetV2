# core/handlers/message_handler.py

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from telethon import TelegramClient, events
from telethon.tl.types import User, PeerUser
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config.settings.base import settings
from storage.database import get_db
from storage.models.base import Session, SessionStatus
from core.engine.conversation_manager import conversation_manager
from core.integrations.telegram_client import TelegramSessionManager
from loguru import logger


class MessageHandler:
    """Обработчик входящих сообщений из Telegram"""

    def __init__(self):
        self.session_manager = TelegramSessionManager()
        self.active_handlers: Dict[str, TelegramClient] = {}
        self.processing_queue = asyncio.Queue()
        self.response_delays: Dict[str, datetime] = {}

    async def initialize(self):
        """Инициализация обработчика"""
        try:
            await self.session_manager.initialize()
            await self._setup_session_handlers()

            # Запускаем обработчик очереди
            asyncio.create_task(self._process_message_queue())

            logger.info("✅ MessageHandler инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации MessageHandler: {e}")
            raise

    async def _setup_session_handlers(self):
        """Настройка обработчиков для всех активных сессий"""
        async with get_db() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(Session).where(
                    Session.status == SessionStatus.ACTIVE,
                    Session.ai_enabled == True
                )
            )
            sessions = result.scalars().all()

            for session in sessions:
                try:
                    await self._setup_session_handler(session)
                except Exception as e:
                    logger.error(f"❌ Ошибка настройки сессии {session.session_name}: {e}")

    async def _setup_session_handler(self, session: Session):
        """Настройка обработчика для конкретной сессии"""

        session_name = session.session_name

        # Получаем клиент для сессии
        client = await self.session_manager.get_client(session_name)
        if not client:
            logger.error(f"❌ Не удалось получить клиент для сессии {session_name}")
            return

        # Регистрируем обработчик новых сообщений
        @client.on(events.NewMessage(incoming=True))
        async def handle_new_message(event):
            try:
                # Проверяем что это личное сообщение от пользователя
                if not isinstance(event.peer_id, PeerUser):
                    return

                sender = await event.get_sender()
                if not isinstance(sender, User) or sender.bot:
                    return

                # Получаем username отправителя
                username = sender.username
                if not username:
                    username = str(sender.id)

                message_text = event.message.message
                if not message_text or len(message_text.strip()) < 1:
                    return

                # Добавляем в очередь обработки
                await self.processing_queue.put({
                    "session_name": session_name,
                    "username": username,
                    "message": message_text,
                    "telegram_id": sender.id,
                    "timestamp": datetime.utcnow()
                })

                logger.info(f"📨 Новое сообщение: {username} → {session_name}")

            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения в сессии {session_name}: {e}")

        self.active_handlers[session_name] = client
        logger.info(f"🎧 Обработчик настроен для сессии {session_name}")

    async def _process_message_queue(self):
        """Обработка очереди сообщений"""
        while True:
            try:
                # Получаем сообщение из очереди
                message_data = await self.processing_queue.get()

                # Обрабатываем сообщение
                await self._handle_message(message_data)

                # Помечаем задачу как выполненную
                self.processing_queue.task_done()

            except Exception as e:
                logger.error(f"❌ Ошибка в очереди обработки сообщений: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, message_data: Dict):
        """Обработка конкретного сообщения"""

        # Проверяем глобальный флаг
        from bot.handlers.ai_control.ai_control import GLOBAL_AI_ENABLED
        if not GLOBAL_AI_ENABLED:
            return

        session_name = message_data["session_name"]
        username = message_data["username"]
        message_text = message_data["message"]

        try:
            # Проверяем задержку перед ответом
            delay_key = f"{session_name}:{username}"
            if delay_key in self.response_delays:
                next_response_time = self.response_delays[delay_key]
                if datetime.utcnow() < next_response_time:
                    wait_seconds = (next_response_time - datetime.utcnow()).total_seconds()
                    logger.info(f"⏳ Задержка ответа для {username}: {wait_seconds:.1f}с")
                    await asyncio.sleep(wait_seconds)

            # Получаем или создаем диалог
            conversation = await conversation_manager.get_conversation(
                lead_username=username,
                session_name=session_name,
                create_if_not_exists=True
            )
            # НОВОЕ: Проверяем фильтр диалогов
            from core.filters.conversation_filter import conversation_filter

            should_respond, reason = await conversation_filter.should_respond_to_conversation(
                conversation, message_text
            )

            if not should_respond:
                logger.info(f"🚫 Пропуск диалога {conversation.id}: {reason}")

                # Если диалог требует одобрения - уведомляем админов
                if "одобрения" in reason:
                    await self._notify_admins_about_pending_approval(conversation, message_text)

                return

            # Проверяем настройки диалога и сессии
            if (conversation.ai_disabled or
                    conversation.auto_responses_paused or
                    not conversation.session.ai_enabled):
                return

            # После получения диалога добавить проверки:
            if conversation.ai_disabled or conversation.auto_responses_paused:
                logger.info(f"⏸️ ИИ отключен для диалога {conversation.id}")
                return

            # Проверяем что ИИ включен для сессии
            if not conversation.session.ai_enabled:
                logger.info(f"📴 ИИ отключен для сессии {conversation.session.session_name}")
                return

            if not conversation:
                logger.error(f"❌ Не удалось создать диалог {username} ↔ {session_name}")
                return

            # Обрабатываем сообщение и генерируем ответ
            response_text = await conversation_manager.process_user_message(
                conversation_id=conversation.id,
                message_text=message_text
            )

            if response_text:
                # Добавляем человекоподобную задержку перед отправкой
                typing_delay = self._calculate_typing_delay(response_text)
                await asyncio.sleep(typing_delay)

                # Отправляем ответ
                await self._send_response(session_name, username, response_text)

                # Устанавливаем задержку для следующего ответа
                next_delay = random.randint(
                    settings.security.response_delay_min,
                    settings.security.response_delay_max
                )
                self.response_delays[delay_key] = datetime.utcnow() + timedelta(seconds=next_delay)

                await self._cancel_pending_followups(conversation.id)

                logger.success(f"✅ Ответ отправлен: {session_name} → {username}")

            else:
                logger.warning(f"⚠️ Не удалось сгенерировать ответ для {username}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения от {username}: {e}")

    async def _cancel_pending_followups(self, conversation_id: int):
        """Отмена ожидающих фолоуапов при ответе пользователя"""
        try:
            from storage.database import get_db
            from storage.models.base import FollowupSchedule
            from sqlalchemy import update

            async with get_db() as db:
                # Отменяем все неисполненные фолоуапы для этого диалога
                await db.execute(
                    update(FollowupSchedule)
                    .where(
                        FollowupSchedule.conversation_id == conversation_id,
                        FollowupSchedule.executed == False
                    )
                    .values(
                        executed=True,
                        executed_at=datetime.utcnow(),
                        generated_message="Отменено - пользователь ответил"
                    )
                )
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка отмены фолоуапов: {e}")

    def _calculate_typing_delay(self, text: str) -> float:
        """Расчет задержки печатания (имитация человека)"""
        # Базовая задержка + время на "печатание"
        base_delay = random.uniform(2, 5)
        typing_speed = random.uniform(3, 7)  # символов в секунду
        typing_delay = len(text) / typing_speed

        # Ограничиваем максимальную задержку
        total_delay = min(base_delay + typing_delay, 15)

        return total_delay

    async def _send_response(self, session_name: str, username: str, text: str):
        """Отправка ответа через Telegram"""

        try:
            client = self.active_handlers.get(session_name)
            if not client:
                logger.error(f"❌ Клиент для сессии {session_name} не найден")
                return False

            # Отправляем сообщение
            await client.send_message(username, text)
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения от {session_name} к {username}: {e}")
            return False

    async def add_session(self, session_name: str):
        """Добавление новой сессии в обработчик"""
        async with get_db() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(Session).where(Session.session_name == session_name)
            )
            session = result.scalar_one_or_none()

            if session and session.ai_enabled:
                await self._setup_session_handler(session)
                logger.info(f"➕ Добавлена сессия в обработчик: {session_name}")

    async def remove_session(self, session_name: str):
        """Удаление сессии из обработчика"""
        if session_name in self.active_handlers:
            client = self.active_handlers[session_name]
            await client.disconnect()
            del self.active_handlers[session_name]
            logger.info(f"➖ Удалена сессия из обработчика: {session_name}")

    async def pause_session(self, session_name: str):
        """Приостановка обработки сессии"""
        # TODO: Реализовать приостановку без отключения клиента
        pass

    async def resume_session(self, session_name: str):
        """Возобновление обработки сессии"""
        # TODO: Реализовать возобновление
        pass

    async def get_active_sessions(self) -> List[str]:
        """Получение списка активных сессий"""
        return list(self.active_handlers.keys())

    async def get_session_stats(self) -> Dict[str, Dict]:
        """Получение статистики по сессиям"""
        stats = {}

        for session_name in self.active_handlers:
            # TODO: Добавить реальную статистику
            stats[session_name] = {
                "status": "active",
                "messages_processed": 0,
                "last_activity": datetime.utcnow().isoformat()
            }

        return stats

    async def _notify_admins_about_pending_approval(self, conversation: Conversation, message_text: str):
        """Уведомление админов о диалоге требующем одобрения"""

        try:
            from bot.main import bot_manager

            text = f"""⚠️ <b>Диалог требует одобрения</b>

👤 <b>От:</b> @{conversation.lead.username}
🤖 <b>Сессия:</b> {conversation.session.session_name}

💬 <b>Сообщение:</b>
{message_text[:200]}{'...' if len(message_text) > 200 else ''}

🔍 Проверьте диалог и примите решение"""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Одобрить",
                            callback_data=f"approve_conversation_{conversation.id}"
                        ),
                        InlineKeyboardButton(
                            text="🚫 Отклонить",
                            callback_data=f"reject_conversation_{conversation.id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="👤 Посмотреть диалог",
                            callback_data=f"dialog_view_{conversation.id}"
                        )
                    ]
                ]
            )

            await bot_manager.broadcast_to_admins(text, keyboard)

        except Exception as e:
            logger.error(f"❌ Ошибка уведомления админов: {e}")

    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Завершение работы MessageHandler...")

        # Отключаем все клиенты
        for session_name, client in self.active_handlers.items():
            try:
                await client.disconnect()
                logger.info(f"🔌 Отключен клиент {session_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка отключения {session_name}: {e}")

        self.active_handlers.clear()
        await self.session_manager.shutdown()

        logger.info("✅ MessageHandler завершен")


# Глобальный экземпляр обработчика
message_handler = MessageHandler()