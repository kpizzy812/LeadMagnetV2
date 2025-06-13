#!/usr/bin/env python3
# scripts/session_manager.py - ИСПРАВЛЕННАЯ БЕЗОПАСНАЯ ВЕРСИЯ

"""
Скрипт для безопасного управления Telegram сессиями
"""

import asyncio
import sys
import json
from pathlib import Path
from typing import Dict, Optional, List
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
import getpass
import socks

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings.base import settings
from storage.database import db_manager, get_db
from storage.models.base import Session, SessionStatus, PersonaType
from sqlalchemy import select
from loguru import logger


class SafeSessionManager:
    """БЕЗОПАСНЫЙ менеджер для работы с сессиями"""

    def __init__(self):
        self.sessions_dir = settings.sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    async def create_session(
            self,
            session_name: str,
            phone: str,
            persona_type: str = "basic_man",
            proxy: Optional[Dict] = None
    ) -> bool:
        """БЕЗОПАСНОЕ создание новой сессии"""

        try:
            session_file = self.sessions_dir / f"{session_name}.session"

            if session_file.exists():
                logger.error(f"❌ Сессия {session_name} уже существует")
                return False

            # ИСПРАВЛЕНИЕ: Получаем прокси из JSON если не передан явно
            if not proxy:
                proxy = await self._load_proxy_config_for_creation(session_name)

            # КРИТИЧНО: НЕ создаём сессию без прокси!
            if not proxy:
                logger.error(f"🚫 КРИТИЧНО: Для {session_name} не найден прокси!")
                logger.error(f"🚫 Создание сессии БЕЗ ПРОКСИ может привести к блокировке!")
                logger.error(f"🚫 Добавьте прокси в команду или настройте в proxies.json")
                return False

            # Создаем клиент с прокси
            proxy_tuple = (
                socks.SOCKS5,
                proxy["host"],
                proxy["port"],
                True,
                proxy.get("username"),
                proxy.get("password")
            )

            logger.info(f"📡 Создание сессии {session_name} через прокси {proxy['host']}:{proxy['port']}")

            client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy_tuple
            )

            logger.info(f"📱 Подключение к Telegram для {phone}...")

            # ИСПРАВЛЕНИЕ: Используем только start() - он уже делает всё что нужно
            await client.start(phone=phone)

            # КРИТИЧНО: НЕ вызываем get_me() и другие API методы!
            # Просто проверяем что авторизация прошла
            if await client.is_user_authorized():
                logger.success(f"✅ Авторизация успешна для {session_name}")

                # Сразу отключаемся, не делая лишних запросов
                await client.disconnect()

                # ИСПРАВЛЕНИЕ: Добавляем в БД с минимальными данными
                # НЕ получаем информацию о пользователе через API
                await self._register_session_minimal(session_name, persona_type)

                # Сохраняем прокси если есть
                if proxy:
                    await self._save_proxy_config(session_name, proxy)

                logger.success(f"✅ Сессия {session_name} создана безопасно!")
                return True
            else:
                logger.error(f"❌ Авторизация не удалась для {session_name}")
                await client.disconnect()
                return False

        except SessionPasswordNeededError:
            logger.error(f"❌ Требуется двухфакторная аутентификация для {phone}")
            password = getpass.getpass("Введите пароль 2FA: ")
            try:
                await client.start(phone=phone, password=password)

                if await client.is_user_authorized():
                    logger.success(f"✅ Авторизация с 2FA успешна для {session_name}")
                    await client.disconnect()

                    await self._register_session_minimal(session_name, persona_type)

                    if proxy:
                        await self._save_proxy_config(session_name, proxy)

                    return True
                else:
                    await client.disconnect()
                    return False

            except Exception as e:
                logger.error(f"❌ Ошибка 2FA: {e}")
                await client.disconnect()
                return False

        except FloodWaitError as e:
            logger.error(f"❌ Флуд контроль: ждите {e.seconds} секунд")
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка создания сессии: {e}")
            try:
                await client.disconnect()
            except:
                pass
            return False

    async def _register_session_minimal(self, session_name: str, persona_type: str):
        """Регистрация сессии в БД с минимальными данными"""
        try:
            async with get_db() as db:
                # ИСПРАВЛЕНИЕ: НЕ получаем данные через API, создаём с минимумом
                new_session = Session(
                    session_name=session_name,
                    persona_type=persona_type,
                    status=SessionStatus.ACTIVE,
                    telegram_id=None,  # Заполним позже когда понадобится
                    username=None,  # Заполним позже
                    first_name=None,  # Заполним позже
                    last_name=None,  # Заполним позже
                    ai_enabled=True
                )

                db.add(new_session)
                await db.commit()

                logger.info(f"✅ Сессия {session_name} добавлена в БД (минимальные данные)")

        except Exception as e:
            logger.error(f"❌ Ошибка добавления в БД: {e}")

    async def _save_proxy_config(self, session_name: str, proxy: Dict):
        """Сохранение конфигурации прокси"""

        proxy_file = settings.data_dir / "proxies.json"

        try:
            # Загружаем существующие прокси
            if proxy_file.exists():
                with open(proxy_file, 'r', encoding='utf-8') as f:
                    proxies = json.load(f)
            else:
                proxies = {}

            # Добавляем новый прокси
            proxies[f"{session_name}.session"] = {
                "static": proxy
            }

            # Сохраняем обратно
            with open(proxy_file, 'w', encoding='utf-8') as f:
                json.dump(proxies, f, indent=2, ensure_ascii=False)

            logger.info(f"📡 Прокси для {session_name} сохранен")

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения прокси: {e}")

    async def update_session_info(self, session_name: str) -> bool:
        """Безопасное обновление информации о сессии (ОТДЕЛЬНО от создания)"""

        try:
            # Загружаем прокси
            proxy = await self._load_proxy_for_session(session_name)

            session_file = self.sessions_dir / f"{session_name}.session"
            if not session_file.exists():
                logger.error(f"❌ Файл сессии {session_name} не найден")
                return False

            client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy
            )

            await client.connect()

            if not await client.is_user_authorized():
                logger.error(f"❌ Сессия {session_name} не авторизована")
                await client.disconnect()
                return False

            # Получаем информацию о пользователе
            me = await client.get_me()
            await client.disconnect()

            # Обновляем в БД
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if session:
                    session.telegram_id = str(me.id)
                    session.username = me.username
                    session.first_name = me.first_name
                    session.last_name = me.last_name

                    await db.commit()
                    logger.success(f"✅ Информация о сессии {session_name} обновлена")
                    return True
                else:
                    logger.error(f"❌ Сессия {session_name} не найдена в БД")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления информации: {e}")
            return False

    async def _load_proxy_config_for_creation(self, session_name: str) -> Optional[Dict]:
        """Загрузка прокси из конфигурации для создания сессии"""
        try:
            proxy_file = settings.data_dir / "proxies.json"
            if not proxy_file.exists():
                logger.warning(f"⚠️ Файл proxies.json не найден")
                return None

            with open(proxy_file, 'r', encoding='utf-8') as f:
                proxies = json.load(f)

            session_key = f"{session_name}.session"
            if session_key not in proxies:
                logger.warning(f"⚠️ Прокси для {session_key} не найден в конфигурации")
                return None

            session_config = proxies[session_key]
            proxy_config = session_config.get("static") or session_config.get("dynamic")

            if not proxy_config or "host" not in proxy_config:
                logger.warning(f"⚠️ Некорректная конфигурация прокси для {session_name}")
                return None

            logger.info(
                f"📡 Загружен прокси для {session_name}: {proxy_config['host']}:{proxy_config.get('port', 'unknown')}")
            return proxy_config

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки прокси для {session_name}: {e}")
            return None
        """Загрузка прокси для сессии"""
        try:
            proxy_file = settings.data_dir / "proxies.json"
            if not proxy_file.exists():
                return None

            with open(proxy_file, 'r', encoding='utf-8') as f:
                proxies = json.load(f)

            session_key = f"{session_name}.session"
            if session_key not in proxies:
                return None

            proxy_config = proxies[session_key].get("static") or proxies[session_key].get("dynamic")
            if not proxy_config:
                return None

            return (
                socks.SOCKS5,
                proxy_config["host"],
                proxy_config["port"],
                True,
                proxy_config.get("username"),
                proxy_config.get("password")
            )

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки прокси: {e}")
            return None

    async def list_sessions(self) -> List[Dict]:
        """Список всех сессий"""

        try:
            sessions = []
            await db_manager.initialize()

            # Сканируем файлы сессий
            session_files = list(self.sessions_dir.rglob("*.session"))

            async with get_db() as db:
                for session_file in session_files:
                    session_name = session_file.stem

                    # Получаем данные из БД
                    result = await db.execute(
                        select(Session).where(Session.session_name == session_name)
                    )
                    db_session = result.scalar_one_or_none()

                    # НЕ проверяем авторизацию автоматически (это может быть подозрительно)
                    session_info = {
                        "name": session_name,
                        "file_path": str(session_file),
                        "authorized": "unknown",  # Не проверяем автоматически
                        "in_database": db_session is not None,
                        "status": db_session.status if db_session else "unknown",
                        "persona": db_session.persona_type if db_session else None,
                        "username": db_session.username if db_session else None,
                        "ai_enabled": db_session.ai_enabled if db_session else False
                    }

                    sessions.append(session_info)

            return sessions

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка сессий: {e}")
            return []

    async def check_session_auth(self, session_name: str) -> bool:
        """ОТДЕЛЬНАЯ безопасная проверка авторизации (только когда нужно)"""

        try:
            session_file = self.sessions_dir / f"{session_name}.session"
            if not session_file.exists():
                return False

            proxy = await self._load_proxy_for_session(session_name)

            client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy
            )

            await client.connect()
            is_authorized = await client.is_user_authorized()
            await client.disconnect()

            # Пауза после проверки
            await asyncio.sleep(1)

            return is_authorized

        except Exception as e:
            logger.error(f"❌ Ошибка проверки авторизации {session_name}: {e}")
            return False

    async def delete_session(self, session_name: str) -> bool:
        """Удаление сессии"""

        try:
            # Удаляем файл
            session_file = self.sessions_dir / f"{session_name}.session"
            if session_file.exists():
                session_file.unlink()
                logger.info(f"🗑️ Файл сессии {session_name} удален")

            # Удаляем из БД
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if session:
                    await db.delete(session)
                    await db.commit()
                    logger.info(f"🗑️ Сессия {session_name} удалена из БД")

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка удаления сессии: {e}")
            return False


async def main():
    """Главная функция"""

    if len(sys.argv) < 2:
        print("🔧 Безопасное управление Telegram сессиями")
        print()
        print("Команды:")
        print("  create <name> <phone> [persona] [proxy_json]  - создать сессию")
        print("  list                                          - список сессий")
        print("  check <name>                                  - проверить авторизацию")
        print("  update <name>                                 - обновить информацию")
        print("  delete <name>                                 - удалить сессию")
        print()
        print("Примеры:")
        print("  python scripts/session_manager.py create test +79111234567 basic_man")
        print("  python scripts/session_manager.py check test")
        return

    command = sys.argv[1]
    manager = SafeSessionManager()

    try:
        await db_manager.initialize()

        if command == "create":
            if len(sys.argv) < 4:
                print("❌ Необходимы: session_name phone [persona] [proxy_json]")
                return

            session_name = sys.argv[2]
            phone = sys.argv[3]
            persona_type = sys.argv[4] if len(sys.argv) > 4 else "basic_man"

            proxy = None
            if len(sys.argv) > 5:
                try:
                    proxy = json.loads(sys.argv[5])
                except:
                    print("❌ Неверный формат JSON для прокси")
                    return

            success = await manager.create_session(session_name, phone, persona_type, proxy)
            if success:
                print(f"✅ Сессия {session_name} создана успешно!")
                print("💡 Подождите 2-3 минуты перед использованием")
            else:
                print(f"❌ Не удалось создать сессию {session_name}")

        elif command == "list":
            sessions = await manager.list_sessions()

            if not sessions:
                print("❌ Сессии не найдены")
                return

            print(f"📋 Найдено {len(sessions)} сессий:")
            print()

            for session in sessions:
                status_icon = "✅" if session["in_database"] else "❌"
                auth_icon = "🔑" if session["authorized"] == True else "❓" if session[
                                                                                 "authorized"] == "unknown" else "🚫"
                ai_icon = "🤖" if session["ai_enabled"] else "📴"

                print(
                    f"{status_icon} {auth_icon} {ai_icon} {session['name']:<20} | {session['persona'] or 'no_persona':<12} | @{session['username'] or 'unknown'}")

        elif command == "check":
            if len(sys.argv) < 3:
                print("❌ Необходимо: session_name")
                return

            session_name = sys.argv[2]
            is_authorized = await manager.check_session_auth(session_name)

            if is_authorized:
                print(f"✅ Сессия {session_name} авторизована")
            else:
                print(f"❌ Сессия {session_name} НЕ авторизована")

        elif command == "update":
            if len(sys.argv) < 3:
                print("❌ Необходимо: session_name")
                return

            session_name = sys.argv[2]
            success = await manager.update_session_info(session_name)

            if success:
                print(f"✅ Информация о сессии {session_name} обновлена")
            else:
                print(f"❌ Не удалось обновить информацию о сессии {session_name}")

        elif command == "delete":
            if len(sys.argv) < 3:
                print("❌ Необходимо: session_name")
                return

            session_name = sys.argv[2]

            confirm = input(f"Вы уверены что хотите удалить сессию {session_name}? (yes/no): ")
            if confirm.lower() in ['yes', 'y', 'да', 'д']:
                success = await manager.delete_session(session_name)

                if success:
                    print(f"✅ Сессия {session_name} удалена")
                else:
                    print(f"❌ Не удалось удалить сессию {session_name}")
            else:
                print("❌ Удаление отменено")

        else:
            print(f"❌ Неизвестная команда: {command}")

    except Exception as e:
        logger.error(f"💥 Ошибка выполнения команды: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Операция прервана")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")