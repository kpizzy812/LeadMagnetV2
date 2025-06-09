# core/integrations/telegram_client.py

import asyncio
import json
from pathlib import Path
from typing import Dict, Optional, List, Any
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, AuthKeyUnregisteredError
import socks

from config.settings.base import settings
from loguru import logger


class ProxyManager:
    """Менеджер прокси"""

    def __init__(self):
        self.proxies: Dict[str, Dict] = {}
        self._load_proxies()

    def _load_proxies(self):
        """Загрузка прокси из конфигурации"""
        proxy_file = settings.data_dir / "proxies.json"
        if proxy_file.exists():
            try:
                with open(proxy_file, 'r', encoding='utf-8') as f:
                    self.proxies = json.load(f)
                logger.info(f"📡 Загружено {len(self.proxies)} прокси конфигураций")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки прокси: {e}")

    def get_proxy_for_session(self, session_name: str) -> Optional[tuple]:
        """Получение прокси для сессии"""
        proxy_config = self.proxies.get(session_name, {}).get("static")
        if not proxy_config:
            return None

        return (
            socks.SOCKS5,
            proxy_config["host"],
            proxy_config["port"],
            True,
            proxy_config["username"],
            proxy_config["password"]
        )


class TelegramSessionManager:
    """Менеджер Telegram сессий"""

    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.proxy_manager = ProxyManager()
        self.session_locks: Dict[str, asyncio.Lock] = {}

    async def initialize(self):
        """Инициализация менеджера"""
        logger.info("🚀 Инициализация TelegramSessionManager")

        # Создаем директорию для сессий если её нет
        settings.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Сканируем существующие сессии
        await self._scan_existing_sessions()

    async def _scan_existing_sessions(self):
        """Сканирование существующих .session файлов"""
        session_files = list(settings.sessions_dir.rglob("*.session"))

        logger.info(f"🔍 Найдено {len(session_files)} session файлов")

        for session_file in session_files:
            session_name = session_file.stem

            # Проверяем авторизацию сессии
            is_authorized = await self._check_session_auth(session_file)

            if is_authorized:
                logger.info(f"✅ Сессия авторизована: {session_name}")
            else:
                logger.warning(f"⚠️ Сессия НЕ авторизована: {session_name}")

    async def _check_session_auth(self, session_file: Path) -> bool:
        """Проверка авторизации сессии"""
        session_name = session_file.stem

        try:
            proxy = self.proxy_manager.get_proxy_for_session(session_name)

            client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy
            )

            await client.connect()
            is_authorized = await client.is_user_authorized()
            await client.disconnect()

            return is_authorized

        except Exception as e:
            logger.error(f"❌ Ошибка проверки авторизации {session_name}: {e}")
            return False

    async def get_client(self, session_name: str) -> Optional[TelegramClient]:
        """Получение клиента для сессии"""

        # Проверяем есть ли уже активный клиент
        if session_name in self.clients:
            client = self.clients[session_name]
            if client.is_connected():
                return client
            else:
                # Клиент отключен, удаляем его
                del self.clients[session_name]

        # Создаем новый клиент
        return await self._create_client(session_name)

    async def _create_client(self, session_name: str) -> Optional[TelegramClient]:
        """Создание нового клиента"""

        # Блокировка для предотвращения одновременного создания клиентов
        if session_name not in self.session_locks:
            self.session_locks[session_name] = asyncio.Lock()

        async with self.session_locks[session_name]:
            # Двойная проверка после получения блокировки
            if session_name in self.clients:
                return self.clients[session_name]

            try:
                # Ищем файл сессии
                session_file = self._find_session_file(session_name)
                if not session_file:
                    logger.error(f"❌ Файл сессии не найден: {session_name}")
                    return None

                # Получаем прокси
                proxy = self.proxy_manager.get_proxy_for_session(session_name)

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

                # Сохраняем клиент
                self.clients[session_name] = client

                logger.info(f"✅ Клиент создан для сессии: {session_name}")
                return client

            except AuthKeyUnregisteredError:
                logger.error(f"❌ Сессия {session_name} заблокирована или недействительна")
                return None

            except Exception as e:
                logger.error(f"❌ Ошибка создания клиента {session_name}: {e}")
                return None

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
            logger.info(f"📤 Сообщение отправлено: {session_name} → {username}")
            return True

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
                "is_authorized": await client.is_user_authorized()
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о сессии {session_name}: {e}")
            return None

    async def disconnect_session(self, session_name: str):
        """Отключение сессии"""
        if session_name in self.clients:
            client = self.clients[session_name]
            try:
                await client.disconnect()
                logger.info(f"🔌 Сессия отключена: {session_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка отключения сессии {session_name}: {e}")
            finally:
                del self.clients[session_name]

    async def disconnect_all(self):
        """Отключение всех сессий"""
        logger.info("🛑 Отключение всех Telegram сессий...")

        for session_name in list(self.clients.keys()):
            await self.disconnect_session(session_name)

        logger.info("✅ Все сессии отключены")

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

        for session_name, client in self.clients.items():
            try:
                is_healthy = (
                        client.is_connected() and
                        await client.is_user_authorized()
                )
                health_status[session_name] = is_healthy

            except Exception as e:
                logger.error(f"❌ Health check для {session_name}: {e}")
                health_status[session_name] = False

        return health_status

    async def restart_session(self, session_name: str) -> bool:
        """Перезапуск сессии"""
        logger.info(f"🔄 Перезапуск сессии: {session_name}")

        # Отключаем если подключена
        await self.disconnect_session(session_name)

        # Создаем заново
        client = await self._create_client(session_name)
        return client is not None

    async def broadcast_message(
            self,
            session_names: List[str],
            recipients: List[str],
            message: str,
            delay_between: int = 3
    ) -> Dict[str, List[str]]:
        """Рассылка сообщения через несколько сессий"""

        results = {
            "success": [],
            "failed": []
        }

        for session_name in session_names:
            for recipient in recipients:
                try:
                    success = await self.send_message(session_name, recipient, message)

                    if success:
                        results["success"].append(f"{session_name} → {recipient}")
                    else:
                        results["failed"].append(f"{session_name} → {recipient}")

                    # Задержка между отправками
                    if delay_between > 0:
                        await asyncio.sleep(delay_between)

                except Exception as e:
                    logger.error(f"❌ Ошибка рассылки {session_name} → {recipient}: {e}")
                    results["failed"].append(f"{session_name} → {recipient}")

        return results

    async def shutdown(self):
        """Корректное завершение работы"""
        await self.disconnect_all()
        self.session_locks.clear()
        logger.info("✅ TelegramSessionManager завершен")


# Глобальный экземпляр менеджера сессий
telegram_session_manager = TelegramSessionManager()