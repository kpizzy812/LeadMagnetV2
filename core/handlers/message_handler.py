# core/handlers/message_handler.py - ИСПРАВЛЕННАЯ ВЕРСИЯ с интеграцией utils

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from telethon import TelegramClient, events
from telethon.tl.types import User, PeerUser
from telethon.errors import (
    NetworkMigrateError, PhoneMigrateError, FloodWaitError,
    AuthKeyUnregisteredError, AuthKeyInvalidError, AuthKeyDuplicatedError,
    ServerError
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from config.settings.base import settings
from storage.database import get_db
from storage.models.base import Session, SessionStatus, Conversation
from core.engine.conversation_manager import conversation_manager
from core.integrations.telegram_client import TelegramSessionManager
from loguru import logger

# ИНТЕГРАЦИЯ: Импорты utils системы
from utils.reconnect_system import reconnect_manager
from utils.dialog_recovery import dialog_recovery
from utils.proxy_validator import proxy_validator


class MessageHandler:
    """Обработчик входящих сообщений из Telegram с системой восстановления"""

    def __init__(self):
        self.session_manager = TelegramSessionManager()
        self.active_handlers: Dict[str, TelegramClient] = {}
        self.processing_queue = asyncio.Queue()
        self.response_delays: Dict[str, datetime] = {}
        self.paused_sessions: Set[str] = set()  # Приостановленные сессии
        self.session_stats: Dict[str, Dict] = {}  # Статистика по сессиям

        # НОВОЕ: Мониторинг соединений
        self.connection_monitors: Dict[str, asyncio.Task] = {}
        self.last_heartbeat: Dict[str, datetime] = {}

    async def initialize(self):
        """Инициализация обработчика с системой восстановления"""
        try:
            await self.session_manager.initialize()

            # НОВОЕ: Инициализация систем восстановления
            await self._initialize_recovery_systems()

            await self._setup_session_handlers()

            # Запускаем обработчик очереди
            asyncio.create_task(self._process_message_queue())

            # НОВОЕ: Запускаем воркер восстановления диалогов
            asyncio.create_task(dialog_recovery.start_recovery_worker())

            # НОВОЕ: Запускаем мониторинг соединений
            asyncio.create_task(self._connection_monitor_loop())

            logger.info("✅ MessageHandler инициализирован с системой восстановления")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации MessageHandler: {e}")
            raise

    async def _initialize_recovery_systems(self):
        """Инициализация систем восстановления"""
        try:
            # Валидируем все прокси
            await proxy_validator.validate_all_from_config()

            # Регистрируем все сессии в reconnect_manager
            session_files = list(settings.sessions_dir.rglob("*.session"))

            for session_file in session_files:
                session_name = session_file.stem

                # Регистрируем callback для переподключения
                reconnect_manager.register_session(
                    session_name,
                    lambda sn=session_name: self._reconnect_session(sn)
                )

            logger.info(f"🔧 Зарегистрировано {len(session_files)} сессий в системе восстановления")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации систем восстановления: {e}")
            raise

    async def _reconnect_session(self, session_name: str) -> bool:
        """Переподключение сессии через session_manager"""
        try:
            logger.info(f"🔄 Переподключение сессии {session_name}")

            # Удаляем старый обработчик
            if session_name in self.active_handlers:
                try:
                    await self.active_handlers[session_name].disconnect()
                except:
                    pass
                del self.active_handlers[session_name]

            # Останавливаем мониторинг соединения
            if session_name in self.connection_monitors:
                self.connection_monitors[session_name].cancel()
                del self.connection_monitors[session_name]

            # Получаем сессию из БД
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if session and session.ai_enabled:
                    # Настраиваем новый обработчик
                    await self._setup_session_handler(session)

                    # Сканируем пропущенные сообщения
                    client = self.active_handlers.get(session_name)
                    if client:
                        asyncio.create_task(self._scan_missed_messages(session_name, client))

                    logger.success(f"✅ Сессия {session_name} переподключена")
                    return True

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка переподключения сессии {session_name}: {e}")
            return False

    async def _scan_missed_messages(self, session_name: str, client: TelegramClient):
        """Сканирование пропущенных сообщений после переподключения"""
        try:
            # Даем время клиенту стабилизироваться
            await asyncio.sleep(3)

            logger.info(f"🔍 Сканирование пропущенных сообщений для {session_name}")

            # Используем dialog_recovery для сканирования
            missed_messages = await dialog_recovery.scan_missed_messages(session_name, client)

            if missed_messages:
                logger.info(f"📬 Найдено {len(missed_messages)} пропущенных сообщений для {session_name}")
                await dialog_recovery.process_missed_messages(missed_messages)
            else:
                logger.info(f"✅ Пропущенных сообщений для {session_name} не найдено")

        except Exception as e:
            logger.error(f"❌ Ошибка сканирования пропущенных сообщений {session_name}: {e}")

    async def _setup_session_handlers(self):
        """Настройка обработчиков для всех активных сессий"""
        async with get_db() as db:
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
                    # НОВОЕ: Отмечаем сессию как отключенную для переподключения
                    reconnect_manager.mark_disconnected(session.session_name)

    async def _setup_session_handler(self, session: Session):
        """Настройка обработчика для конкретной сессии с мониторингом"""
        session_name = session.session_name

        # Получаем клиент для сессии
        client = await self.session_manager.get_client(session_name)
        if not client:
            logger.error(f"❌ Не удалось получить клиент для сессии {session_name}")
            reconnect_manager.mark_disconnected(session_name)
            return

        # НОВОЕ: Настраиваем мониторинг соединения
        self._start_connection_monitor(session_name, client)

        # Регистрируем обработчик новых сообщений с защитой от ошибок
        @client.on(events.NewMessage(incoming=True))
        async def handle_new_message(event):
            try:
                # Обновляем heartbeat
                self.last_heartbeat[session_name] = datetime.utcnow()

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

            except (NetworkMigrateError, PhoneMigrateError, ServerError, ConnectionError) as e:
                logger.error(f"🔌 Ошибка соединения для {session_name}: {e}")
                # Отмечаем как отключенную для переподключения
                reconnect_manager.mark_disconnected(session_name)

            except (AuthKeyUnregisteredError, AuthKeyInvalidError, AuthKeyDuplicatedError) as e:
                logger.error(f"🚫 Ошибка авторизации для {session_name}: {e}")
                # Критическая ошибка - не пытаемся переподключаться

            except FloodWaitError as e:
                logger.warning(f"⏰ Flood wait для {session_name}: {e.seconds}с")

            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения в сессии {session_name}: {e}")

        self.active_handlers[session_name] = client

        # Отмечаем как подключенную
        reconnect_manager.mark_connected(session_name)

        logger.info(f"🎧 Обработчик настроен для сессии {session_name}")

    def _start_connection_monitor(self, session_name: str, client: TelegramClient):
        """Запуск мониторинга соединения для сессии"""

        async def monitor_connection():
            """Мониторинг соединения сессии"""
            try:
                while session_name in self.active_handlers:
                    await asyncio.sleep(30)  # Проверка каждые 30 секунд

                    try:
                        # Проверяем что клиент подключен
                        if not client.is_connected():
                            logger.warning(f"⚠️ Клиент {session_name} отключен")
                            reconnect_manager.mark_disconnected(session_name)
                            break

                        # Проверяем авторизацию
                        if not await client.is_user_authorized():
                            logger.warning(f"⚠️ Клиент {session_name} потерял авторизацию")
                            reconnect_manager.mark_disconnected(session_name)
                            break

                        # Проверяем heartbeat (последняя активность)
                        last_heartbeat = self.last_heartbeat.get(session_name)
                        if last_heartbeat:
                            inactive_time = datetime.utcnow() - last_heartbeat
                            if inactive_time > timedelta(hours=1):
                                logger.info(f"💤 Сессия {session_name} неактивна {inactive_time}")

                    except (NetworkMigrateError, PhoneMigrateError, ServerError, ConnectionError) as e:
                        logger.error(f"🔌 Ошибка мониторинга соединения {session_name}: {e}")
                        reconnect_manager.mark_disconnected(session_name)
                        break

                    except Exception as e:
                        logger.error(f"❌ Ошибка мониторинга {session_name}: {e}")
                        await asyncio.sleep(60)  # Пауза при ошибке

            except asyncio.CancelledError:
                logger.info(f"🛑 Мониторинг {session_name} остановлен")
            except Exception as e:
                logger.error(f"❌ Критическая ошибка мониторинга {session_name}: {e}")

        # Запускаем задачу мониторинга
        task = asyncio.create_task(monitor_connection())
        self.connection_monitors[session_name] = task

        # Инициализируем heartbeat
        self.last_heartbeat[session_name] = datetime.utcnow()

    async def _connection_monitor_loop(self):
        """Основной цикл мониторинга всех соединений"""
        while True:
            try:
                await asyncio.sleep(120)  # Проверка каждые 2 минуты

                # Проверяем здоровье всех активных сессий
                for session_name in list(self.active_handlers.keys()):
                    client = self.active_handlers[session_name]

                    try:
                        # Быстрая проверка соединения
                        if not client.is_connected():
                            logger.warning(f"⚠️ Обнаружено отключение {session_name}")
                            reconnect_manager.mark_disconnected(session_name)

                    except Exception as e:
                        logger.error(f"❌ Ошибка проверки соединения {session_name}: {e}")
                        reconnect_manager.mark_disconnected(session_name)

                # Очищаем неактивные мониторы
                await self._cleanup_inactive_monitors()

            except Exception as e:
                logger.error(f"❌ Ошибка в цикле мониторинга соединений: {e}")
                await asyncio.sleep(60)

    async def _cleanup_inactive_monitors(self):
        """Очистка неактивных мониторов"""
        inactive_monitors = []

        for session_name, task in self.connection_monitors.items():
            if task.done() or session_name not in self.active_handlers:
                inactive_monitors.append(session_name)

        for session_name in inactive_monitors:
            if session_name in self.connection_monitors:
                task = self.connection_monitors[session_name]
                if not task.done():
                    task.cancel()
                del self.connection_monitors[session_name]

        if inactive_monitors:
            logger.info(f"🧹 Очищено {len(inactive_monitors)} неактивных мониторов")

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

            # Проверяем фильтр диалогов
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

            # Дополнительные проверки состояния диалога
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

                # Отправляем ответ через безопасный метод
                success = await self._send_response_safely(session_name, username, response_text)

                if success:
                    # Устанавливаем задержку для следующего ответа
                    next_delay = random.randint(
                        settings.security.response_delay_min,
                        settings.security.response_delay_max
                    )
                    self.response_delays[delay_key] = datetime.utcnow() + timedelta(seconds=next_delay)

                    # Отменяем фолоуапы только при успешной отправке
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

    async def _send_response_safely(self, session_name: str, username: str, message_text: str) -> bool:
        """БЕЗОПАСНАЯ отправка ответа с обработкой ошибок соединения"""
        try:
            # Проверяем что сессия активна
            if session_name not in self.active_handlers:
                logger.error(f"❌ Сессия {session_name} не активна")
                return False

            client = self.active_handlers[session_name]

            # Проверяем соединение перед отправкой
            if not client.is_connected():
                logger.warning(f"⚠️ Клиент {session_name} отключен, попытка переподключения")
                reconnect_manager.mark_disconnected(session_name)
                return False

            # Отправляем сообщение
            await client.send_message(username, message_text)

            # Обновляем heartbeat
            self.last_heartbeat[session_name] = datetime.utcnow()

            logger.info(f"📤 Сообщение отправлено: {session_name} → @{username}")

            # Обновляем статистику сессии
            await self._update_session_stats(session_name, success=True)

            return True

        except (NetworkMigrateError, PhoneMigrateError, ServerError, ConnectionError) as e:
            logger.error(f"🔌 Ошибка соединения при отправке {session_name} → @{username}: {e}")
            reconnect_manager.mark_disconnected(session_name)
            await self._update_session_stats(session_name, success=False)
            return False

        except FloodWaitError as e:
            logger.warning(f"⏰ Flood wait для {session_name}: {e.seconds}с")
            await self._update_session_stats(session_name, success=False)
            return False

        except (AuthKeyUnregisteredError, AuthKeyInvalidError, AuthKeyDuplicatedError) as e:
            logger.error(f"🚫 Ошибка авторизации {session_name}: {e}")
            await self._update_session_stats(session_name, success=False)
            return False

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

            # Останавливаем мониторинг
            if session_name in self.connection_monitors:
                self.connection_monitors[session_name].cancel()
                del self.connection_monitors[session_name]

            await client.disconnect()
            del self.active_handlers[session_name]

            # Очищаем heartbeat
            if session_name in self.last_heartbeat:
                del self.last_heartbeat[session_name]

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

                    # Определяем статус с учетом reconnect_manager
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

                    # НОВОЕ: Дополнительная информация о соединении
                    connection_info = {
                        "has_monitor": session_name in self.connection_monitors,
                        "last_heartbeat": self.last_heartbeat.get(session_name),
                        "reconnect_state": reconnect_manager.session_states.get(session_name,
                                                                                "unknown").value if hasattr(
                            reconnect_manager.session_states.get(session_name, "unknown"), 'value') else str(
                            reconnect_manager.session_states.get(session_name, "unknown"))
                    }

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
                        "connection_info": connection_info,
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

            # НОВОЕ: Информация о системе восстановления
            stats["recovery_info"] = {
                "reconnect_retries": reconnect_manager.retry_counts.get(session_name, 0),
                "last_reconnect_attempt": reconnect_manager.last_attempt.get(session_name),
                "has_reconnect_task": session_name in reconnect_manager.reconnect_tasks
            }

            return stats

        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса сессии {session_name}: {e}")
            return {"error": str(e)}

    async def cleanup_inactive_sessions(self):
        """Очистка неактивных сессий с системой восстановления"""
        try:
            inactive_sessions = []

            for session_name in list(self.active_handlers.keys()):
                client = self.active_handlers[session_name]

                if not client.is_connected():
                    inactive_sessions.append(session_name)
                    # Отмечаем как отключенную для переподключения
                    reconnect_manager.mark_disconnected(session_name)
                    continue

                try:
                    is_authorized = await client.is_user_authorized()
                    if not is_authorized:
                        inactive_sessions.append(session_name)
                        reconnect_manager.mark_disconnected(session_name)
                except:
                    inactive_sessions.append(session_name)
                    reconnect_manager.mark_disconnected(session_name)

            # Удаляем неактивные сессии (они будут переподключены автоматически)
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
                "connection_monitors": len(self.connection_monitors),
                "last_updated": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики в реальном времени: {e}")
            return {}

    async def emergency_disconnect_all(self):
        """Экстренное отключение всех сессий"""
        logger.warning("🚨 ЭКСТРЕННОЕ ОТКЛЮЧЕНИЕ ВСЕХ СЕССИЙ")

        try:
            # Останавливаем все мониторы
            for task in self.connection_monitors.values():
                task.cancel()
            self.connection_monitors.clear()

            # Отключаем все клиенты
            disconnect_tasks = []
            for session_name in list(self.active_handlers.keys()):
                task = asyncio.create_task(self.remove_session(session_name))
                disconnect_tasks.append(task)

            if disconnect_tasks:
                await asyncio.gather(*disconnect_tasks, return_exceptions=True)

            logger.info("✅ Все сессии экстренно отключены")

        except Exception as e:
            logger.error(f"❌ Ошибка экстренного отключения: {e}")

    async def force_reconnect_all(self):
        """Принудительное переподключение всех сессий"""
        logger.info("🔄 Принудительное переподключение всех сессий")

        try:
            session_names = list(self.active_handlers.keys())

            for session_name in session_names:
                logger.info(f"🔄 Переподключение {session_name}")
                reconnect_manager.mark_disconnected(session_name)

            logger.info(f"✅ Запущено переподключение {len(session_names)} сессий")

        except Exception as e:
            logger.error(f"❌ Ошибка принудительного переподключения: {e}")

    async def get_recovery_stats(self) -> Dict[str, Any]:
        """Получение статистики системы восстановления"""
        try:
            return {
                "reconnect_manager": {
                    "registered_sessions": len(reconnect_manager.session_states),
                    "active_reconnect_tasks": len(reconnect_manager.reconnect_tasks),
                    "session_states": {
                        name: state.value if hasattr(state, 'value') else str(state)
                        for name, state in reconnect_manager.session_states.items()
                    },
                    "retry_counts": reconnect_manager.retry_counts.copy()
                },
                "dialog_recovery": {
                    "recovery_queue_size": dialog_recovery.recovery_queue.qsize(),
                    "last_scan_times": {
                        session: time.isoformat() if isinstance(time, datetime) else str(time)
                        for session, time in dialog_recovery.last_scan_time.items()
                    }
                },
                "message_handler": {
                    "active_handlers": len(self.active_handlers),
                    "connection_monitors": len(self.connection_monitors),
                    "heartbeats": {
                        session: time.isoformat() if isinstance(time, datetime) else str(time)
                        for session, time in self.last_heartbeat.items()
                    }
                }
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики восстановления: {e}")
            return {"error": str(e)}

    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Завершение работы MessageHandler...")

        # Останавливаем все мониторы соединений
        for task in self.connection_monitors.values():
            task.cancel()

        # Ждем завершения мониторов
        if self.connection_monitors:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.connection_monitors.values(), return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("⏰ Таймаут завершения мониторов соединений")

        self.connection_monitors.clear()

        # Отключаем все клиенты
        for session_name, client in self.active_handlers.items():
            try:
                await client.disconnect()
                logger.info(f"🔌 Отключен клиент {session_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка отключения {session_name}: {e}")

        self.active_handlers.clear()

        # Завершаем session_manager
        await self.session_manager.shutdown()

        # Завершаем reconnect_manager
        await reconnect_manager.shutdown()

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