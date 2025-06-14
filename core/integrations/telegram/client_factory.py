# core/integrations/telegram/client_factory.py
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError, SessionPasswordNeededError, FloodWaitError,
    AuthKeyInvalidError, AuthKeyDuplicatedError
)
from loguru import logger

from config.settings.base import settings
from .proxy_manager import ProxyManager


class TelegramClientFactory:
    """Фабрика для создания и валидации Telegram клиентов"""

    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager

    async def create_client(self, session_name: str, session_file: Path) -> Optional[TelegramClient]:
        """Безопасное создание клиента с полными проверками"""
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

    async def validate_session_file(self, session_file: Path) -> bool:
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