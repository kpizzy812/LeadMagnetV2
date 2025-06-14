# core/integrations/telegram/session_manager.py
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.tl.types import User, PeerUser
from telethon.errors import FloodWaitError
from loguru import logger

from config.settings.base import settings
from .proxy_manager import ProxyManager
from .client_factory import TelegramClientFactory
from .connection_monitor import ConnectionMonitor


class TelegramSessionManager:
    """РЕФАКТОРЕННЫЙ менеджер Telegram сессий"""

    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.session_locks: Dict[str, asyncio.Lock] = {}
        self.session_states: Dict[str, Dict[str, Any]] = {}
        self.last_activity: Dict[str, datetime] = {}
        self.shutdown_event = asyncio.Event()
        self.cleanup_task: Optional[asyncio.Task] = None

        # Компоненты
        self.proxy_manager = ProxyManager()
        self.client_factory = TelegramClientFactory(self.proxy_manager)
        self.connection_monitor = ConnectionMonitor()

    async def initialize(self):
        """Инициализация с проверкой безопасности"""
        logger.info("🔧 Инициализация безопасного Telegram Session Manager...")

        # Создаем папки если их нет
        settings.sessions_dir.mkdir(parents=True, exist_ok=True)

        # КРИТИЧНО: Проверяем что все сессии имеют прокси
        await self._validate_all_session_proxies()

        # Сканируем доступные сессии
        await self._scan_available_sessions()

        # Запускаем задачу очистки неактивных соединений
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

        # Интеграция с utils системами
        await self._integrate_with_utils()

        logger.success("✅ Безопасный Telegram Session Manager инициализирован")

    async def _integrate_with_utils(self):
        """Интеграция с utils системами"""
        try:
            # Интеграция с proxy_validator
            from utils.proxy_validator import proxy_validator
            await proxy_validator.validate_all_from_config()

            # Интеграция с dialog_recovery
            from utils.dialog_recovery import dialog_recovery
            asyncio.create_task(dialog_recovery.start_recovery_worker())

            # Интеграция с reconnect_manager
            from utils.reconnect_system import reconnect_manager

            # Регистрируем все сессии в reconnect_manager
            session_files = list(settings.sessions_dir.rglob("*.session"))
            for session_file in session_files:
                session_name = session_file.stem
                reconnect_manager.register_session(
                    session_name,
                    lambda sn=session_name: self._reconnect_session(sn)
                )

            logger.info("🔗 Интеграция с utils системами завершена")

        except Exception as e:
            logger.error(f"❌ Ошибка интеграции с utils: {e}")

    async def _reconnect_session(self, session_name: str) -> bool:
        """Реконнект сессии"""
        try:
            logger.info(f"🔄 Попытка переподключения {session_name}")

            # Удаляем старый клиент
            if session_name in self.clients:
                try:
                    await self.clients[session_name].disconnect()
                except:
                    pass
                del self.clients[session_name]

            # Останавливаем мониторинг
            self.connection_monitor.stop_monitoring(session_name)

            # Создаем новый клиент
            client = await self.get_client(session_name)

            if client:
                # Сканируем пропущенные сообщения
                asyncio.create_task(self._scan_missed_for_session(session_name, client))
                return True
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка переподключения {session_name}: {e}")
            return False

    async def _scan_missed_for_session(self, session_name: str, client):
        """Сканирование пропущенных сообщений для сессии"""
        try:
            # Даем время клиенту полностью подключиться
            await asyncio.sleep(5)

            # Сканируем пропущенные сообщения
            from utils.dialog_recovery import dialog_recovery
            missed_messages = await dialog_recovery.scan_missed_messages(session_name, client)

            if missed_messages:
                await dialog_recovery.process_missed_messages(missed_messages)

        except Exception as e:
            logger.error(f"❌ Ошибка сканирования пропущенных сообщений {session_name}: {e}")

    async def _validate_all_session_proxies(self):
        """Валидация прокси для всех сессий"""
        logger.info("🔍 Проверка конфигурации прокси для всех сессий...")

        proxy_status = self.proxy_manager.get_all_session_proxy_status()

        safe_sessions = []
        unsafe_sessions = []

        for session_name, status in proxy_status.items():
            if status["static_valid"] or status["dynamic_valid"]:
                safe_sessions.append(session_name)
                proxy_info = status.get("proxy_info", "unknown")
                logger.info(f"✅ {session_name}: {proxy_info}")
            else:
                unsafe_sessions.append(session_name)
                errors = ", ".join(status["errors"]) if status["errors"] else "нет конфигурации"
                logger.error(f"🚫 {session_name}: {errors}")

        if unsafe_sessions:
            logger.error(f"🚫 КРИТИЧНО: Найдено {len(unsafe_sessions)} сессий БЕЗ валидных прокси!")
            logger.error(f"🚫 Небезопасные сессии: {', '.join(unsafe_sessions)}")

        logger.info(f"📊 Итого: {len(safe_sessions)} безопасных, {len(unsafe_sessions)} небезопасных сессий")

    async def _scan_available_sessions(self):
        """Сканирование доступных сессий с проверкой прокси"""
        session_files = list(settings.sessions_dir.rglob("*.session"))

        if not session_files:
            logger.warning("⚠️ Не найдено файлов сессий")
            return

        logger.info(f"📁 Найдено {len(session_files)} файлов сессий")

        # Проверяем каждую сессию БЕЗ создания постоянных соединений
        for session_file in session_files:
            session_name = session_file.stem

            # Проверяем что есть прокси
            proxy_valid = self.proxy_manager.enforce_proxy_requirement(session_name)

            if proxy_valid:
                # Проверяем валидность файла сессии
                is_valid = await self.client_factory.validate_session_file(session_file)

                if is_valid:
                    logger.info(f"✅ Сессия готова: {session_name}")
                    self.session_states[session_name] = {
                        'file_path': session_file,
                        'status': 'ready',
                        'last_check': datetime.now(),
                        'has_proxy': True
                    }
                else:
                    logger.warning(f"⚠️ Проблема с файлом сессии: {session_name}")
            else:
                logger.error(f"🚫 Сессия {session_name} заблокирована из-за отсутствия прокси")

    async def get_client(self, session_name: str) -> Optional[TelegramClient]:
        """БЕЗОПАСНОЕ получение клиента для сессии"""

        # КРИТИЧНО: Проверяем прокси перед созданием клиента
        if not self.proxy_manager.enforce_proxy_requirement(session_name):
            return None

        # Создаем блокировку для сессии если её нет
        if session_name not in self.session_locks:
            self.session_locks[session_name] = asyncio.Lock()

        async with self.session_locks[session_name]:
            # Проверяем существующий клиент под блокировкой
            if session_name in self.clients:
                client = self.clients[session_name]
                if client.is_connected():
                    # Обновляем время последней активности
                    self.last_activity[session_name] = datetime.now()
                    return client
                else:
                    # Клиент отключен, безопасно удаляем его
                    await self._safe_disconnect(session_name)

            # Создаем новый клиент
            return await self._create_client_safely(session_name)

    async def _create_client_safely(self, session_name: str) -> Optional[TelegramClient]:
        """БЕЗОПАСНОЕ создание клиента с полными проверками"""

        # Проверяем что сессия готова
        if session_name not in self.session_states:
            logger.error(f"❌ Сессия {session_name} не найдена в готовых к использованию")
            return None

        session_info = self.session_states[session_name]
        session_file = session_info['file_path']

        # Создаем клиент через фабрику
        client = await self.client_factory.create_client(session_name, session_file)

        if not client:
            return None

        # Настраиваем обработчики событий
        await self._setup_event_handlers(client, session_name)

        # Запускаем мониторинг соединения
        self.connection_monitor.start_monitoring(
            session_name,
            client,
            self._handle_connection_lost
        )

        # Сохраняем клиент
        self.clients[session_name] = client
        self.last_activity[session_name] = datetime.now()

        # Уведомляем reconnect_manager о подключении
        try:
            from utils.reconnect_system import reconnect_manager
            reconnect_manager.mark_connected(session_name)
        except:
            pass

        logger.success(f"✅ Безопасный клиент создан для сессии: {session_name}")
        return client

    async def _handle_connection_lost(self, session_name: str, reason: str):
        """Обработка потери соединения"""
        logger.warning(f"🔌 Потеря соединения {session_name}: {reason}")

        try:
            # Уведомляем reconnect_manager
            from utils.reconnect_system import reconnect_manager
            reconnect_manager.mark_disconnected(session_name)
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления reconnect_manager: {e}")

    async def _setup_event_handlers(self, client: TelegramClient, session_name: str):
        """Настройка обработчиков событий для клиента"""

        @client.on(events.NewMessage(incoming=True))
        async def handle_new_message(event):
            """Обработчик новых сообщений"""
            try:
                # Обновляем heartbeat в мониторе
                self.connection_monitor.update_heartbeat(session_name)

                # Обновляем время активности
                self.last_activity[session_name] = datetime.now()

                # Импортируем здесь чтобы избежать циклических импортов
                from core.handlers.message_handler import message_handler

                # Передаем сообщение в обработчик
                await message_handler.handle_incoming_message(
                    session_name,
                    event
                )

            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения для {session_name}: {e}")

    async def _safe_disconnect(self, session_name: str):
        """Безопасное отключение сессии"""
        try:
            # Останавливаем мониторинг
            self.connection_monitor.stop_monitoring(session_name)

            if session_name in self.clients:
                client = self.clients[session_name]
                if client.is_connected():
                    await client.disconnect()
                del self.clients[session_name]

            if session_name in self.last_activity:
                del self.last_activity[session_name]

            logger.info(f"🔌 Сессия {session_name} отключена")
        except Exception as e:
            logger.error(f"❌ Ошибка отключения сессии {session_name}: {e}")

    async def _cleanup_loop(self):
        """Цикл очистки неактивных соединений"""
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                await self._cleanup_inactive_sessions()
                await self.connection_monitor.cleanup_inactive_monitors()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле очистки: {e}")

    async def _cleanup_inactive_sessions(self):
        """Очистка неактивных сессий"""
        try:
            current_time = datetime.now()
            inactive_sessions = []

            for session_name, last_activity in self.last_activity.items():
                if current_time - last_activity > timedelta(hours=1):
                    inactive_sessions.append(session_name)

            for session_name in inactive_sessions:
                logger.info(f"🧹 Очистка неактивной сессии: {session_name}")
                await self._safe_disconnect(session_name)

        except Exception as e:
            logger.error(f"❌ Ошибка очистки неактивных сессий: {e}")

    async def send_message(self, session_name: str, username: str, message: str) -> bool:
        """Отправка сообщения через сессию"""

        client = await self.get_client(session_name)
        if not client:
            logger.error(f"❌ Не удалось получить клиент для {session_name}")
            return False

        try:
            await client.send_message(username, message)

            # Обновляем активность и heartbeat
            self.last_activity[session_name] = datetime.now()
            self.connection_monitor.update_heartbeat(session_name)

            logger.success(f"📤 Сообщение отправлено: {session_name} → {username}")
            return True

        except FloodWaitError as e:
            logger.warning(f"⏰ Flood wait {e.seconds}с для {session_name}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения {session_name} → {username}: {e}")
            return False

    async def get_session_info(self, session_name: str) -> Optional[Dict[str, Any]]:
        """Получение информации о сессии"""

        client = await self.get_client(session_name)
        if not client:
            return None

        try:
            me = await client.get_me()

            # Получаем статус соединения
            connection_status = self.connection_monitor.get_status(session_name)

            return {
                "session_name": session_name,
                "telegram_id": me.id,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "phone": me.phone,
                "is_premium": getattr(me, 'premium', False),
                "is_verified": getattr(me, 'verified', False),
                "is_connected": client.is_connected(),
                "last_activity": self.last_activity.get(session_name),
                "connection_status": connection_status
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о сессии {session_name}: {e}")
            return None

    async def get_active_sessions(self) -> List[str]:
        """Получение списка активных сессий"""
        active_sessions = []

        for session_name, client in self.clients.items():
            if client.is_connected():
                active_sessions.append(session_name)

        return active_sessions

    async def health_check(self) -> Dict[str, bool]:
        """Проверка здоровья всех сессий"""
        health_status = {}

        for session_name in self.session_states.keys():
            try:
                session_info = self.session_states[session_name]
                session_file = session_info['file_path']

                is_healthy = await self.client_factory.validate_session_file(session_file)
                health_status[session_name] = is_healthy

            except Exception as e:
                logger.error(f"❌ Ошибка проверки здоровья {session_name}: {e}")
                health_status[session_name] = False

        return health_status

    def get_session_states(self) -> Dict[str, Dict[str, Any]]:
        """Получение состояний всех сессий"""
        states = {}

        for session_name, state in self.session_states.items():
            connection_status = self.connection_monitor.get_status(session_name)

            states[session_name] = {
                **state,
                'is_connected': session_name in self.clients and self.clients[session_name].is_connected(),
                'last_activity': self.last_activity.get(session_name),
                'connection_status': connection_status
            }

        return states

    async def cleanup_inactive_sessions(self):
        """Публичный метод очистки неактивных сессий"""
        await self._cleanup_inactive_sessions()

    async def shutdown(self):
        """Корректное завершение всех сессий"""
        logger.info("🛑 Завершение Telegram Session Manager...")

        # Сигнализируем о завершении
        self.shutdown_event.set()

        # Останавливаем задачу очистки
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        # Завершаем мониторинг соединений
        await self.connection_monitor.shutdown()

        # Корректно отключаем все клиенты
        disconnect_tasks = []
        for session_name in list(self.clients.keys()):
            task = asyncio.create_task(self._safe_disconnect(session_name))
            disconnect_tasks.append(task)

        if disconnect_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*disconnect_tasks, return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("⏰ Таймаут отключения сессий")

        self.clients.clear()
        self.session_locks.clear()
        self.session_states.clear()

        logger.success("✅ Все Telegram сессии корректно отключены")


# Глобальный экземпляр менеджера
telegram_session_manager = TelegramSessionManager()