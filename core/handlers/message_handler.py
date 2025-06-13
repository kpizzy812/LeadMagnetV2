# core/handlers/message_handler.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from telethon import TelegramClient, events
from telethon.tl.types import User, PeerUser
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from config.settings.base import settings
from storage.database import get_db
from storage.models.base import Session, SessionStatus, Conversation
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
        self.paused_sessions: Set[str] = set()  # Приостановленные сессии
        self.session_stats: Dict[str, Dict] = {}  # Статистика по сессиям

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
            logger.info("🚫 Глобальный ИИ отключен")
            return

        session_name = message_data["session_name"]
        username = message_data["username"]
        message_text = message_data["message"]

        if session_name in self.paused_sessions:
            logger.info(f"⏸️ Сессия {session_name} приостановлена, пропускаем сообщение")
            return

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

            if not conversation:
                logger.error(f"❌ Не удалось создать диалог {username} ↔ {session_name}")
                return

            # ИСПРАВЛЕНИЕ: Проверяем фильтр диалогов
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

            # ИСПРАВЛЕНИЕ: Дополнительные проверки состояния диалога
            if (conversation.ai_disabled or
                    conversation.auto_responses_paused or
                    not conversation.session.ai_enabled):
                logger.info(f"⏸️ ИИ отключен для диалога {conversation.id}")
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

                # ИСПРАВЛЕНИЕ: Отправляем ответ через исправленный метод
                success = await self._send_response(session_name, username, response_text)

                if success:
                    # Устанавливаем задержку для следующего ответа
                    next_delay = random.randint(
                        settings.security.response_delay_min,
                        settings.security.response_delay_max
                    )
                    self.response_delays[delay_key] = datetime.utcnow() + timedelta(seconds=next_delay)

                    # ИСПРАВЛЕНИЕ: Отменяем фолоуапы только при успешной отправке
                    await self._cancel_pending_followups(conversation.id)

                    logger.success(f"✅ Ответ отправлен: {session_name} → {username}")
                else:
                    logger.error(f"❌ Не удалось отправить ответ {session_name} → {username}")

            else:
                logger.warning(f"⚠️ Не удалось сгенерировать ответ для {username}")

            if session_name in self.session_stats:
                self.session_stats[session_name]["last_activity"] = datetime.utcnow().isoformat()
                self.session_stats[session_name]["messages_24h"] = self.session_stats[session_name].get("messages_24h",
                                                                                                        0) + 1

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения от {username}: {e}")

    async def _send_response(self, session_name: str, username: str, message_text: str) -> bool:
        """ИСПРАВЛЕНИЕ: Добавляем недостающий метод отправки ответа"""
        try:
            # Используем session_manager для отправки сообщения
            success = await self.session_manager.send_message(
                session_name=session_name,
                username=username,
                message=message_text
            )

            if success:
                logger.info(f"📤 Сообщение отправлено: {session_name} → @{username}")

                # Обновляем статистику сессии
                await self._update_session_stats(session_name, success=True)

            return success

        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения {session_name} → @{username}: {e}")
            await self._update_session_stats(session_name, success=False)
            return False

    async def _update_session_stats(self, session_name: str, success: bool = True):
        """Обновление статистики сессии"""
        try:
            async with get_db() as db:
                from sqlalchemy import update

                # Обновляем статистику в базе данных
                if success:
                    await db.execute(
                        update(Session)
                        .where(Session.session_name == session_name)
                        .values(
                            total_messages_sent=Session.total_messages_sent + 1,
                            last_activity=datetime.utcnow()
                        )
                    )
                    await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики сессии {session_name}: {e}")

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

    async def _notify_admins_about_pending_approval(self, conversation: Conversation, message_text: str):
        """Уведомление админов о диалоге требующем одобрения"""

        try:
            from bot.main import bot_manager

            # Ограничиваем длину сообщения
            truncated_message = message_text[:200] + "..." if len(message_text) > 200 else message_text

            text = f"""⚠️ <b>Новый диалог требует одобрения</b>

👤 <b>От:</b> @{conversation.lead.username}
🤖 <b>Сессия:</b> {conversation.session.session_name}
🎭 <b>Персона:</b> {conversation.session.persona_type or 'не задана'}

💬 <b>Сообщение:</b>
<code>{truncated_message}</code>

🔍 <b>Что делать?</b>
• Одобрить - ИИ начнет отвечать
• Отклонить - диалог будет заблокирован"""

            # ИСПРАВЛЕНИЕ: Используем правильный импорт для клавиатуры
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Одобрить и ответить",
                            callback_data=f"approve_conversation_{conversation.id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="👁️ Посмотреть диалог",
                            callback_data=f"dialog_view_{conversation.id}"
                        ),
                        InlineKeyboardButton(
                            text="🚫 Отклонить",
                            callback_data=f"reject_conversation_{conversation.id}"
                        )
                    ]
                ]
            )

            await bot_manager.broadcast_to_admins(text, keyboard)
            logger.info(f"📨 Админы уведомлены о диалоге {conversation.id}")

        except Exception as e:
            logger.error(f"❌ Ошибка уведомления админов: {e}")

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
        try:
            if session_name not in self.active_handlers:
                logger.warning(f"⚠️ Сессия {session_name} не активна")
                return False

            # Добавляем в список приостановленных
            self.paused_sessions.add(session_name)

            # Обновляем статус в БД
            async with get_db() as db:
                from sqlalchemy import update
                await db.execute(
                    update(Session)
                    .where(Session.session_name == session_name)
                    .values(ai_enabled=False)
                )
                await db.commit()

            # Обновляем статистику
            if session_name in self.session_stats:
                self.session_stats[session_name]["status"] = "paused"

            logger.info(f"⏸️ Сессия {session_name} приостановлена")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка приостановки сессии {session_name}: {e}")
            return False

    async def resume_session(self, session_name: str):
        """Возобновление обработки сессии"""
        try:
            # Убираем из списка приостановленных
            self.paused_sessions.discard(session_name)

            # Обновляем статус в БД
            async with get_db() as db:
                from sqlalchemy import update
                await db.execute(
                    update(Session)
                    .where(Session.session_name == session_name)
                    .values(ai_enabled=True)
                )
                await db.commit()

            # Если сессия не активна - добавляем
            if session_name not in self.active_handlers:
                await self.add_session(session_name)

            # Обновляем статистику
            if session_name in self.session_stats:
                self.session_stats[session_name]["status"] = "active"

            logger.info(f"▶️ Сессия {session_name} возобновлена")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка возобновления сессии {session_name}: {e}")
            return False

    async def get_session_stats(self) -> Dict[str, Dict]:
        """Получение статистики по сессиям"""
        try:
            # Обновляем статистику из БД
            await self._update_session_stats_from_db()

            # Возвращаем актуальную статистику
            return self.session_stats.copy()

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики сессий: {e}")
            return {}

    async def _update_session_stats_from_db(self):
        """Обновление статистики сессий из БД"""
        try:
            async with get_db() as db:
                from sqlalchemy import select, func
                from storage.models.base import Session, Conversation, Message as DBMessage

                # Получаем статистику по сессиям
                result = await db.execute(
                    select(
                        Session.session_name,
                        Session.status,
                        Session.ai_enabled,
                        Session.total_conversations,
                        Session.total_messages_sent,
                        Session.total_conversions,
                        Session.last_activity,
                        Session.persona_type
                    ).order_by(Session.session_name)
                )
                sessions_data = result.all()

                # Статистика сообщений за последние 24 часа
                yesterday = datetime.utcnow() - timedelta(hours=24)

                for session_data in sessions_data:
                    session_name = session_data.session_name

                    # Сообщения за 24 часа
                    messages_24h_result = await db.execute(
                        select(func.count(DBMessage.id))
                        .join(Session)
                        .where(
                            Session.session_name == session_name,
                            DBMessage.role == "assistant",
                            DBMessage.created_at >= yesterday
                        )
                    )
                    messages_24h = messages_24h_result.scalar() or 0

                    # Активные диалоги
                    active_dialogs_result = await db.execute(
                        select(func.count(Conversation.id))
                        .join(Session)
                        .where(
                            Session.session_name == session_name,
                            Conversation.status == "active"
                        )
                    )
                    active_dialogs = active_dialogs_result.scalar() or 0

                    # Определяем статус
                    if session_name in self.paused_sessions:
                        status = "paused"
                    elif session_name in self.active_handlers:
                        client = self.active_handlers[session_name]
                        if client.is_connected() and session_data.ai_enabled:
                            status = "active"
                        else:
                            status = "disconnected"
                    else:
                        status = "inactive"

                    # Обновляем статистику
                    self.session_stats[session_name] = {
                        "status": status,
                        "persona_type": session_data.persona_type,
                        "ai_enabled": session_data.ai_enabled,
                        "total_conversations": session_data.total_conversations or 0,
                        "total_messages": session_data.total_messages_sent or 0,
                        "total_conversions": session_data.total_conversions or 0,
                        "messages_24h": messages_24h,
                        "active_dialogs": active_dialogs,
                        "last_activity": session_data.last_activity.isoformat() if session_data.last_activity else None,
                        "is_connected": session_name in self.active_handlers,
                        "last_updated": datetime.utcnow().isoformat()
                    }

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики из БД: {e}")

    async def get_session_status(self, session_name: str) -> Dict[str, Any]:
        """Получение детального статуса конкретной сессии"""
        try:
            await self._update_session_stats_from_db()

            if session_name not in self.session_stats:
                return {"error": "Session not found"}

            stats = self.session_stats[session_name].copy()

            # Дополнительные проверки
            if session_name in self.active_handlers:
                client = self.active_handlers[session_name]
                stats["client_connected"] = client.is_connected()

                try:
                    stats["client_authorized"] = await client.is_user_authorized()
                except:
                    stats["client_authorized"] = False
            else:
                stats["client_connected"] = False
                stats["client_authorized"] = False

            # Проверяем очередь сообщений
            stats["queue_size"] = self.processing_queue.qsize()

            # Проверяем задержки
            delay_key = f"{session_name}:*"
            stats["has_response_delays"] = any(
                key.startswith(session_name) for key in self.response_delays.keys()
            )

            return stats

        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса сессии {session_name}: {e}")
            return {"error": str(e)}

    async def cleanup_inactive_sessions(self):
        """Очистка неактивных сессий"""
        try:
            inactive_sessions = []

            for session_name in list(self.active_handlers.keys()):
                client = self.active_handlers[session_name]

                if not client.is_connected():
                    inactive_sessions.append(session_name)
                    continue

                try:
                    is_authorized = await client.is_user_authorized()
                    if not is_authorized:
                        inactive_sessions.append(session_name)
                except:
                    inactive_sessions.append(session_name)

            # Удаляем неактивные сессии
            for session_name in inactive_sessions:
                await self.remove_session(session_name)
                logger.warning(f"🧹 Удалена неактивная сессия: {session_name}")

            if inactive_sessions:
                logger.info(f"🧹 Очищено {len(inactive_sessions)} неактивных сессий")

            return len(inactive_sessions)

        except Exception as e:
            logger.error(f"❌ Ошибка очистки неактивных сессий: {e}")
            return 0

    async def get_active_sessions(self) -> List[str]:
        """Получение списка активных сессий"""
        return list(self.active_handlers.keys())

    def get_realtime_stats(self) -> Dict[str, Any]:
        """Получение статистики в реальном времени"""
        try:
            return {
                "active_sessions": len(self.active_handlers),
                "paused_sessions": len(self.paused_sessions),
                "queue_size": self.processing_queue.qsize(),
                "total_response_delays": len(self.response_delays),
                "sessions_list": list(self.active_handlers.keys()),
                "paused_list": list(self.paused_sessions),
                "last_updated": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики в реальном времени: {e}")
            return {}

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

    async def handle_incoming_message(self, session_name: str, event):
        """Метод для совместимости с старым кодом telegram_client.py"""
        try:
            # Проверяем что это личное сообщение от пользователя
            if not hasattr(event, 'peer_id') or not hasattr(event.peer_id, '__class__'):
                return

            from telethon.tl.types import PeerUser, User

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

            # Добавляем в очередь обработки (используем существующую систему)
            await self.processing_queue.put({
                "session_name": session_name,
                "username": username,
                "message": message_text,
                "telegram_id": sender.id,
                "timestamp": datetime.utcnow()
            })

            logger.info(f"📨 Новое сообщение: {username} → {session_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения от {session_name}: {e}")

# Глобальный экземпляр обработчика
message_handler = MessageHandler()