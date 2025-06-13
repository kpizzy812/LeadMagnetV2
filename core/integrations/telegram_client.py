# core/integrations/telegram_client.py - ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ

import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import socks

from telethon import TelegramClient, events
from telethon.errors import (
    AuthKeyUnregisteredError,
    SessionPasswordNeededError,
    FloodWaitError,
    AuthKeyInvalidError,
    AuthKeyDuplicatedError
)
from loguru import logger

from config.settings.base import settings


class ProxyManager:
    """ИСПРАВЛЕННЫЙ менеджер прокси с полной валидацией"""

    def __init__(self):
        self.proxies: Dict[str, Dict] = {}
        self.proxy_validation_cache: Dict[str, bool] = {}
        self._load_proxies()

    def _load_proxies(self):
        """Загрузка прокси из конфигурации с валидацией"""
        proxy_file = settings.data_dir / "proxies.json"
        if proxy_file.exists():
            try:
                with open(proxy_file, 'r', encoding='utf-8') as f:
                    self.proxies = json.load(f)
                logger.info(f"📡 Загружено {len(self.proxies)} прокси конфигураций")

                # Валидируем конфигурацию
                self._validate_proxy_config()

            except Exception as e:
                logger.error(f"❌ Ошибка загрузки прокси: {e}")
        else:
            logger.warning("⚠️ Файл proxies.json не найден! Создайте его для безопасности.")

    def _validate_proxy_config(self):
        """Валидация конфигурации прокси"""

        # Проверяем что все сессии имеют прокси
        session_files = list(settings.sessions_dir.rglob("*.session"))

        missing_proxies = []
        invalid_configs = []
        valid_configs = []

        for session_file in session_files:
            session_name = session_file.stem
            session_key = f"{session_name}.session"

            if session_key not in self.proxies:
                missing_proxies.append(session_name)
                continue

            # Проверяем структуру конфигурации
            session_config = self.proxies[session_key]

            has_static = "static" in session_config
            has_dynamic = "dynamic" in session_config

            if not (has_static or has_dynamic):
                invalid_configs.append(f"{session_name} (нет static/dynamic)")
                continue

            # Проверяем required поля в static конфигурации
            config_valid = False
            if has_static:
                static_config = session_config["static"]
                if "host" in static_config and "port" in static_config:
                    config_valid = True

            # Проверяем dynamic если static невалиден
            if not config_valid and has_dynamic:
                dynamic_config = session_config["dynamic"]
                if "host" in dynamic_config and "port" in dynamic_config:
                    config_valid = True

            if config_valid:
                valid_configs.append(session_name)
            else:
                invalid_configs.append(f"{session_name} (нет host/port)")

        # Логируем результаты валидации
        if valid_configs:
            logger.success(
                f"✅ Валидные прокси ({len(valid_configs)}): {', '.join(valid_configs[:5])}{'...' if len(valid_configs) > 5 else ''}")

        if missing_proxies:
            logger.error(
                f"🚫 Сессии БЕЗ прокси ({len(missing_proxies)}): {', '.join(missing_proxies[:5])}{'...' if len(missing_proxies) > 5 else ''}")

        if invalid_configs:
            logger.error(
                f"❌ Некорректные конфигурации ({len(invalid_configs)}): {', '.join(invalid_configs[:3])}{'...' if len(invalid_configs) > 3 else ''}")

    def get_proxy_for_session(self, session_name: str) -> Optional[tuple]:
        """ИСПРАВЛЕННОЕ получение прокси для сессии"""

        # ИСПРАВЛЕНИЕ: добавляем .session к имени для поиска
        session_key = f"{session_name}.session"
        session_config = self.proxies.get(session_key, {})

        if not session_config:
            logger.error(f"🚫 КРИТИЧНО: Прокси для {session_name} НЕ НАЙДЕН!")
            logger.error(f"🚫 Ожидаемый ключ в proxies.json: '{session_key}'")
            logger.error(f"🚫 Доступные ключи: {list(self.proxies.keys())[:3]}...")
            return None

        # Приоритет: static, потом dynamic
        proxy_config = session_config.get("static") or session_config.get("dynamic")

        if not proxy_config:
            logger.error(f"❌ Конфигурация прокси для {session_name} пуста!")
            return None

        # Проверяем обязательные поля
        required_fields = ["host", "port"]
        for field in required_fields:
            if field not in proxy_config:
                logger.error(f"❌ В прокси для {session_name} отсутствует поле '{field}'!")
                return None

        logger.debug(f"📡 Прокси для {session_name}: {proxy_config['host']}:{proxy_config['port']}")

        return (
            socks.SOCKS5,
            proxy_config["host"],
            proxy_config["port"],
            True,  # requires_auth
            proxy_config.get("username"),
            proxy_config.get("password")
        )

    def validate_session_proxy(self, session_name: str) -> Dict[str, Any]:
        """Детальная валидация прокси для сессии"""

        session_key = f"{session_name}.session"

        result = {
            "session_name": session_name,
            "session_key": session_key,
            "has_config": False,
            "has_static": False,
            "has_dynamic": False,
            "static_valid": False,
            "dynamic_valid": False,
            "proxy_info": None,
            "errors": []
        }

        # Проверяем наличие конфигурации
        if session_key not in self.proxies:
            result["errors"].append(f"Отсутствует ключ '{session_key}' в proxies.json")
            return result

        result["has_config"] = True
        session_config = self.proxies[session_key]

        # Проверяем static конфигурацию
        if "static" in session_config:
            result["has_static"] = True
            static_config = session_config["static"]

            required_fields = ["host", "port"]
            missing_fields = [f for f in required_fields if f not in static_config]

            if not missing_fields:
                result["static_valid"] = True
                result["proxy_info"] = f"{static_config['host']}:{static_config['port']} (static)"
            else:
                result["errors"].append(f"Static: отсутствуют поля {missing_fields}")

        # Проверяем dynamic конфигурацию
        if "dynamic" in session_config:
            result["has_dynamic"] = True
            dynamic_config = session_config["dynamic"]

            required_fields = ["host", "port"]
            missing_fields = [f for f in required_fields if f not in dynamic_config]

            if not missing_fields:
                result["dynamic_valid"] = True
                if not result["proxy_info"]:  # Если static не валиден
                    result["proxy_info"] = f"{dynamic_config['host']}:{dynamic_config['port']} (dynamic)"
            else:
                result["errors"].append(f"Dynamic: отсутствуют поля {missing_fields}")

        return result

    def enforce_proxy_requirement(self, session_name: str) -> bool:
        """СТРОГАЯ проверка: есть ли валидный прокси для сессии"""

        proxy = self.get_proxy_for_session(session_name)

        if not proxy:
            logger.error(f"🚫 БЛОКИРОВКА: Сессия {session_name} не может быть создана без прокси!")
            logger.error(f"🚫 Это необходимо для предотвращения блокировок Telegram!")
            return False

        return True

    def get_all_session_proxy_status(self) -> Dict[str, Dict[str, Any]]:
        """Получение статуса прокси для всех сессий"""

        session_files = list(settings.sessions_dir.rglob("*.session"))
        results = {}

        for session_file in session_files:
            session_name = session_file.stem
            results[session_name] = self.validate_session_proxy(session_name)

        return results


class TelegramSessionManager:
    """ИСПРАВЛЕННЫЙ менеджер Telegram сессий с полной защитой от блокировок"""

    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.proxy_manager = ProxyManager()
        self.session_locks: Dict[str, asyncio.Lock] = {}
        self.session_states: Dict[str, Dict[str, Any]] = {}
        self.last_activity: Dict[str, datetime] = {}
        self.shutdown_event = asyncio.Event()
        self.cleanup_task: Optional[asyncio.Task] = None

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

        logger.success("✅ Безопасный Telegram Session Manager инициализирован")

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
            logger.error(f"🚫 Эти сессии НЕ БУДУТ использоваться до исправления конфигурации!")

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
                is_valid = await self._validate_session_file(session_file)

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

    async def _validate_session_file(self, session_file: Path) -> bool:
        """Проверка валидности файла сессии БЕЗ создания постоянного соединения"""
        session_name = session_file.stem

        try:
            # Получаем прокси
            proxy = self.proxy_manager.get_proxy_for_session(session_name)
            if not proxy:
                return False

            # Создаем временный клиент только для проверки
            temp_client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy
            )

            # Быстрая проверка авторизации
            await temp_client.connect()
            is_authorized = await temp_client.is_user_authorized()

            # КРИТИЧНО: Обязательно отключаемся
            await temp_client.disconnect()

            # Небольшая пауза между проверками
            await asyncio.sleep(0.5)

            return is_authorized

        except (AuthKeyInvalidError, AuthKeyUnregisteredError, AuthKeyDuplicatedError):
            logger.error(f"❌ Сессия {session_name} недействительна или заблокирована")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сессии {session_name}: {e}")
            return False

    async def get_client(self, session_name: str) -> Optional[TelegramClient]:
        """БЕЗОПАСНОЕ получение клиента для сессии с защитой от дублирования"""

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

        try:
            # КРИТИЧНО: Получаем прокси и проверяем что он есть
            proxy = self.proxy_manager.get_proxy_for_session(session_name)
            if not proxy:
                logger.error(f"🚫 БЛОКИРОВКА СОЗДАНИЯ: {session_name} без прокси!")
                return None

            logger.info(f"📡 Создание клиента {session_name} через прокси {proxy[1]}:{proxy[2]}")

            # Создаем клиент
            client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy
            )

            # Подключаемся
            await client.start()

            # Проверяем авторизацию
            if not await client.is_user_authorized():
                logger.error(f"❌ Сессия {session_name} не авторизована")
                await client.disconnect()
                return None

            # Настраиваем обработчики событий
            await self._setup_event_handlers(client, session_name)

            # Сохраняем клиент
            self.clients[session_name] = client
            self.last_activity[session_name] = datetime.now()

            logger.success(f"✅ Безопасный клиент создан для сессии: {session_name}")
            return client

        except AuthKeyUnregisteredError:
            logger.error(f"❌ Сессия {session_name} заблокирована")
            return None
        except AuthKeyDuplicatedError:
            logger.error(f"❌ Сессия {session_name} используется в другом месте")
            return None
        except FloodWaitError as e:
            logger.warning(f"⏰ Ожидание {e.seconds}с для сессии {session_name}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка создания клиента {session_name}: {e}")
            return None

    async def _setup_event_handlers(self, client: TelegramClient, session_name: str):
        """Настройка обработчиков событий для клиента"""

        @client.on(events.NewMessage(incoming=True))
        async def handle_new_message(event):
            """Обработчик новых сообщений"""
            try:
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
            if session_name in self.clients:
                client = self.clients[session_name]
                if client.is_connected():
                    await client.disconnect()
                del self.clients[session_name]
                logger.info(f"🔌 Сессия {session_name} отключена")
        except Exception as e:
            logger.error(f"❌ Ошибка отключения сессии {session_name}: {e}")

    async def _cleanup_loop(self):
        """Цикл очистки неактивных соединений"""
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                await self._cleanup_inactive_sessions()
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
                if session_name in self.last_activity:
                    del self.last_activity[session_name]

        except Exception as e:
            logger.error(f"❌ Ошибка очистки неактивных сессий: {e}")

    async def send_message(
            self,
            session_name: str,
            username: str,
            message: str
    ) -> bool:
        """Отправка сообщения через сессию"""

        client = await self.get_client(session_name)
        if not client:
            logger.error(f"❌ Не удалось получить клиент для {session_name}")
            return False

        try:
            await client.send_message(username, message)
            self.last_activity[session_name] = datetime.now()
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
                "last_activity": self.last_activity.get(session_name)
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
                # Проверяем без создания постоянного соединения
                session_info = self.session_states[session_name]
                session_file = session_info['file_path']

                is_healthy = await self._validate_session_file(session_file)
                health_status[session_name] = is_healthy

            except Exception as e:
                logger.error(f"❌ Ошибка проверки здоровья {session_name}: {e}")
                health_status[session_name] = False

        return health_status

    def get_session_states(self) -> Dict[str, Dict[str, Any]]:
        """Получение состояний всех сессий"""
        states = {}

        for session_name, state in self.session_states.items():
            states[session_name] = {
                **state,
                'is_connected': session_name in self.clients and self.clients[session_name].is_connected(),
                'last_activity': self.last_activity.get(session_name)
            }

        return states

    async def cleanup_inactive_sessions(self):
        """Публичный метод очистки неактивных сессий"""
        await self._cleanup_inactive_sessions()

    # Методы для совместимости с существующим кодом
    async def _check_session_auth(self, session_file: Path) -> bool:
        """Проверка авторизации сессии (для совместимости)"""
        return await self._validate_session_file(session_file)

    def _find_session_file(self, session_name: str) -> Optional[Path]:
        """Поиск файла сессии"""
        # Ищем в основной директории сессий
        session_file = settings.sessions_dir / f"{session_name}.session"
        if session_file.exists():
            return session_file

        # Ищем в подпапках (по ролям)
        for subdir in settings.sessions_dir.iterdir():
            if subdir.is_dir():
                session_file = subdir / f"{session_name}.session"
                if session_file.exists():
                    return session_file

        return None


# Глобальный экземпляр менеджера
telegram_session_manager = TelegramSessionManager()