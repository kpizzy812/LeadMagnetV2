#!/usr/bin/env python3
# scripts/session_manager.py

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

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings.base import settings
from storage.database import db_manager, get_db
from storage.models.base import Session, SessionStatus, PersonaType
from sqlalchemy import select
from loguru import logger


class SessionManager:
    """Менеджер для работы с сессиями"""

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
        """Создание новой сессии"""

        try:
            session_file = self.sessions_dir / f"{session_name}.session"

            if session_file.exists():
                logger.error(f"❌ Сессия {session_name} уже существует")
                return False

            # Создаем клиент с прокси если указан
            proxy_tuple = None
            if proxy:
                import socks
                proxy_tuple = (
                    socks.SOCKS5,
                    proxy["host"],
                    proxy["port"],
                    True,
                    proxy.get("username"),
                    proxy.get("password")
                )

            client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy_tuple
            )

            logger.info(f"📱 Подключение к Telegram для {phone}...")
            await client.start(phone=phone)

            # Получаем информацию о пользователе
            me = await client.get_me()

            # Сохраняем в базу данных
            async with get_db() as db:
                new_session = Session(
                    session_name=session_name,
                    persona_type=persona_type,
                    status=SessionStatus.ACTIVE,
                    telegram_id=str(me.id),
                    username=me.username,
                    first_name=me.first_name,
                    last_name=me.last_name,
                    ai_enabled=True
                )

                db.add(new_session)
                await db.commit()

            await client.disconnect()

            # Сохраняем прокси если есть
            if proxy:
                await self._save_proxy_config(session_name, proxy)

            logger.success(f"✅ Сессия {session_name} создана успешно!")
            logger.info(f"👤 Пользователь: @{me.username} ({me.first_name} {me.last_name})")
            logger.info(f"🎭 Персона: {persona_type}")

            return True

        except SessionPasswordNeededError:
            logger.error("❌ Требуется двухфакторная аутентификация")
            password = getpass.getpass("Введите пароль 2FA: ")
            try:
                await client.start(phone=phone, password=password)
                logger.success("✅ Авторизация с 2FA успешна")
                return True
            except Exception as e:
                logger.error(f"❌ Ошибка 2FA: {e}")
                return False

        except FloodWaitError as e:
            logger.error(f"❌ Флуд контроль: ждите {e.seconds} секунд")
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка создания сессии: {e}")
            return False

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

    async def list_sessions(self) -> List[Dict]:
        """Список всех сессий"""

        try:
            sessions = []

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

                    # Проверяем авторизацию
                    is_authorized = await self._check_session_auth(session_file)

                    session_info = {
                        "name": session_name,
                        "file_path": str(session_file),
                        "authorized": is_authorized,
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

    async def _check_session_auth(self, session_file: Path) -> bool:
        """Проверка авторизации сессии"""

        try:
            client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash
            )

            await client.connect()
            is_authorized = await client.is_user_authorized()
            await client.disconnect()

            return is_authorized

        except Exception:
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
                db_session = result.scalar_one_or_none()

                if db_session:
                    await db.delete(db_session)
                    await db.commit()
                    logger.info(f"🗑️ Сессия {session_name} удалена из БД")

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка удаления сессии: {e}")
            return False

    async def update_persona(self, session_name: str, persona_type: str) -> bool:
        """Обновление персоны сессии"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if not session:
                    logger.error(f"❌ Сессия {session_name} не найдена в БД")
                    return False

                session.persona_type = persona_type
                await db.commit()

                logger.success(f"✅ Персона сессии {session_name} обновлена на {persona_type}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка обновления персоны: {e}")
            return False

    async def set_ref_link(self, session_name: str, ref_link: str) -> bool:
        """Установка реферальной ссылки"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if not session:
                    logger.error(f"❌ Сессия {session_name} не найдена в БД")
                    return False

                session.project_ref_link = ref_link
                await db.commit()

                logger.success(f"✅ Реф ссылка для {session_name} установлена")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка установки реф ссылки: {e}")
            return False


# CLI интерфейс
async def main():
    """Главная функция CLI"""

    # Инициализируем базу данных
    await db_manager.initialize()

    manager = SessionManager()

    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1]

    try:
        if command == "create":
            if len(sys.argv) < 4:
                print(
                    "❌ Использование: python session_manager.py create <имя_сессии> <телефон> [персона] [прокси_json]")
                return

            session_name = sys.argv[2]
            phone = sys.argv[3]
            persona = sys.argv[4] if len(sys.argv) > 4 else "basic_man"

            proxy = None
            if len(sys.argv) > 5:
                try:
                    proxy = json.loads(sys.argv[5])
                except json.JSONDecodeError:
                    logger.error("❌ Неверный формат JSON для прокси")
                    return

            await manager.create_session(session_name, phone, persona, proxy)

        elif command == "list":
            sessions = await manager.list_sessions()

            if not sessions:
                print("📝 Сессий не найдено")
                return

            print("\n📋 Список сессий:")
            print("-" * 80)

            for session in sessions:
                status_emoji = "✅" if session["authorized"] else "❌"
                db_emoji = "💾" if session["in_database"] else "❓"
                ai_emoji = "🤖" if session.get("ai_enabled") else "📴"

                print(f"{status_emoji} {db_emoji} {ai_emoji} {session['name']}")
                print(f"    Персона: {session.get('persona', 'не задана')}")
                print(f"    Username: @{session.get('username', 'неизвестен')}")
                print(f"    Статус: {session.get('status', 'неизвестен')}")
                print(f"    Путь: {session['file_path']}")
                print()

        elif command == "delete":
            if len(sys.argv) < 3:
                print("❌ Использование: python session_manager.py delete <имя_сессии>")
                return

            session_name = sys.argv[2]

            # Подтверждение
            confirm = input(f"⚠️ Удалить сессию {session_name}? (yes/no): ")
            if confirm.lower() in ['yes', 'y', 'да', 'д']:
                await manager.delete_session(session_name)
            else:
                print("❌ Отменено")

        elif command == "persona":
            if len(sys.argv) < 4:
                print("❌ Использование: python session_manager.py persona <имя_сессии> <тип_персоны>")
                print("Доступные персоны: basic_man, basic_woman, hyip_man, hyip_woman, investor_man")
                return

            session_name = sys.argv[2]
            persona_type = sys.argv[3]

            valid_personas = ["basic_man", "basic_woman", "hyip_man", "hyip_woman", "investor_man"]
            if persona_type not in valid_personas:
                print(f"❌ Неверный тип персоны. Доступные: {', '.join(valid_personas)}")
                return

            await manager.update_persona(session_name, persona_type)

        elif command == "reflink":
            if len(sys.argv) < 4:
                print("❌ Использование: python session_manager.py reflink <имя_сессии> <ссылка>")
                return

            session_name = sys.argv[2]
            ref_link = sys.argv[3]

            await manager.set_ref_link(session_name, ref_link)

        elif command == "check":
            sessions = await manager.list_sessions()

            print("\n🔍 Проверка сессий:")
            print("-" * 50)

            for session in sessions:
                status = "✅ Авторизована" if session["authorized"] else "❌ НЕ авторизована"
                print(f"{session['name']}: {status}")

        else:
            print_help()

    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await db_manager.close()


def print_help():
    """Помощь по использованию"""

    help_text = """
🎯 Менеджер Telegram сессий

Команды:
  create <имя> <телефон> [персона] [прокси]  - Создать новую сессию
  list                                        - Список всех сессий  
  delete <имя>                               - Удалить сессию
  persona <имя> <тип>                        - Установить персону
  reflink <имя> <ссылка>                     - Установить реф ссылку
  check                                      - Проверить авторизацию сессий

Примеры:
  python session_manager.py create alex_session +1234567890 basic_man
  python session_manager.py create maria_session +1234567891 basic_woman '{"host":"proxy.com","port":1080,"username":"user","password":"pass"}'
  python session_manager.py list
  python session_manager.py persona alex_session hyip_man
  python session_manager.py reflink alex_session "https://t.me/bot?start=ref123"
  python session_manager.py delete alex_session

Персоны:
  basic_man     - Простой парень
  basic_woman   - Простая девушка  
  hyip_man      - HYIP эксперт
  hyip_woman    - HYIP женщина
  investor_man  - Опытный инвестор

Формат прокси JSON:
  {"host":"proxy.example.com","port":1080,"username":"user","password":"pass"}
"""
    print(help_text)


if __name__ == "__main__":
    asyncio.run(main())