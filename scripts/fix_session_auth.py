#!/usr/bin/env python3
# scripts/fix_session_auth.py - Исправление проблем с авторизацией сессий

"""
Скрипт для диагностики и исправления проблем с Telegram сессиями
"""

import asyncio
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config.settings.base import settings
from storage.database import db_manager, get_db
from storage.models.base import Session, SessionStatus
from sqlalchemy import select, update


class SessionFixer:
    """Исправление проблем с сессиями"""

    def __init__(self):
        self.backup_dir = Path("data/session_backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def run_full_diagnostic(self):
        """Полная диагностика и исправление"""

        print("🔧 Полная диагностика системы сессий")
        print("=" * 60)

        total_issues = 0

        # 1. Проверка файлов сессий
        file_issues = await self.check_session_files()
        total_issues += file_issues

        # 2. Проверка базы данных
        db_issues = await self.check_database_consistency()
        total_issues += db_issues

        # 3. Проверка авторизации
        auth_issues = await self.check_authorization()
        total_issues += auth_issues

        # 4. Проверка дублирования
        duplicate_issues = await self.check_duplicates()
        total_issues += duplicate_issues

        # 5. Очистка старых сессий
        cleanup_issues = await self.cleanup_old_sessions()
        total_issues += cleanup_issues

        print("\n" + "=" * 60)
        if total_issues == 0:
            print("✅ Все сессии в порядке! Проблем не найдено.")
        else:
            print(f"🔧 Найдено и исправлено проблем: {total_issues}")
            print("\n💡 Рекомендации:")
            print("   • Перезапустите систему: python main.py")
            print("   • Проверьте логи: tail -f logs/system.log")

        return total_issues

    async def check_session_files(self) -> int:
        """Проверка файлов сессий"""

        print("📁 Проверка файлов сессий...")

        session_files = list(settings.sessions_dir.rglob("*.session"))

        if not session_files:
            print("   ⚠️ Файлы сессий не найдены")
            return 1

        print(f"   📊 Найдено файлов: {len(session_files)}")

        issues = 0

        for session_file in session_files:
            session_name = session_file.stem

            # Проверяем размер файла
            if session_file.stat().st_size < 100:
                print(f"   ❌ {session_name} - файл слишком мал")
                await self._backup_and_remove_session(session_file)
                issues += 1
                continue

            # Проверяем доступность
            try:
                with open(session_file, 'rb') as f:
                    data = f.read(100)
                    if not data:
                        print(f"   ❌ {session_name} - файл поврежден")
                        await self._backup_and_remove_session(session_file)
                        issues += 1
            except Exception as e:
                print(f"   ❌ {session_name} - ошибка чтения: {e}")
                await self._backup_and_remove_session(session_file)
                issues += 1

        if issues == 0:
            print("   ✅ Все файлы сессий в порядке")

        return issues

    async def check_database_consistency(self) -> int:
        """Проверка консистентности базы данных"""

        print("🗄️ Проверка базы данных...")

        try:
            await db_manager.initialize()

            async with get_db() as db:
                # Получаем все сессии из БД
                result = await db.execute(select(Session))
                db_sessions = result.scalars().all()

                # Получаем файлы сессий
                session_files = list(settings.sessions_dir.rglob("*.session"))
                file_sessions = {f.stem for f in session_files}

                issues = 0

                # Проверяем сессии в БД без файлов
                for db_session in db_sessions:
                    if db_session.session_name not in file_sessions:
                        print(f"   🗑️ Удаляем из БД: {db_session.session_name} (нет файла)")
                        await db.delete(db_session)
                        issues += 1

                # Проверяем файлы без записей в БД
                db_session_names = {s.session_name for s in db_sessions}
                for file_session in file_sessions:
                    if file_session not in db_session_names:
                        print(f"   ➕ Добавляем в БД: {file_session}")
                        # Создаем запись
                        new_session = Session(
                            session_name=file_session,
                            status=SessionStatus.INACTIVE,
                            ai_enabled=True
                        )
                        db.add(new_session)
                        issues += 1

                await db.commit()

                if issues == 0:
                    print("   ✅ База данных консистентна")

                return issues

        except Exception as e:
            print(f"   ❌ Ошибка проверки БД: {e}")
            return 1

    async def check_authorization(self) -> int:
        """Проверка авторизации сессий"""

        print("🔑 Проверка авторизации сессий...")

        try:
            # Используем правильный импорт из вашего проекта
            from core.integrations.telegram_client import TelegramSessionManager

            # Создаем экземпляр менеджера
            session_manager = TelegramSessionManager()
            await session_manager.initialize()

            # Проверяем здоровье всех сессий
            health_status = await session_manager.health_check()

            issues = 0
            authorized_count = 0

            for session_name, is_healthy in health_status.items():
                if is_healthy:
                    print(f"   ✅ {session_name} - авторизована")
                    authorized_count += 1
                else:
                    print(f"   ❌ {session_name} - НЕ авторизована")
                    await self._handle_unauthorized_session(session_name)
                    issues += 1

            print(f"   📊 Авторизовано: {authorized_count}/{len(health_status)}")

            # Завершаем менеджер (добавляем метод disconnect_all если есть)
            if hasattr(session_manager, 'disconnect_all'):
                await session_manager.disconnect_all()

            return issues

        except Exception as e:
            print(f"   ❌ Ошибка проверки авторизации: {e}")
            return 1

    async def check_duplicates(self) -> int:
        """Проверка дублирующихся сессий"""

        print("🔍 Проверка дублирующихся сессий...")

        session_files = list(settings.sessions_dir.rglob("*.session"))
        session_names = [f.stem for f in session_files]

        # Ищем дубликаты по именам
        seen_names = set()
        duplicates = []

        for name in session_names:
            if name in seen_names:
                duplicates.append(name)
            else:
                seen_names.add(name)

        if duplicates:
            print(f"   ⚠️ Найдено дубликатов: {len(duplicates)}")
            for duplicate in duplicates:
                print(f"   🗑️ Удаляем дубликат: {duplicate}")
                # Найдем и удалим дубликаты (оставляем первый)
                duplicate_files = [f for f in session_files if f.stem == duplicate]
                for i, dup_file in enumerate(duplicate_files[1:], 1):
                    await self._backup_and_remove_session(dup_file)
            return len(duplicates)
        else:
            print("   ✅ Дубликатов не найдено")
            return 0

    async def cleanup_old_sessions(self) -> int:
        """Очистка старых неиспользуемых сессий"""

        print("🧹 Очистка старых сессий...")

        try:
            async with get_db() as db:
                # Находим сессии которые давно не использовались
                from sqlalchemy import and_
                from datetime import datetime, timedelta

                old_threshold = datetime.now() - timedelta(days=30)

                result = await db.execute(
                    select(Session).where(
                        and_(
                            Session.status == SessionStatus.INACTIVE,
                            Session.last_activity < old_threshold
                        )
                    )
                )
                old_sessions = result.scalars().all()

                if old_sessions:
                    print(f"   🗑️ Найдено старых сессий: {len(old_sessions)}")
                    for session in old_sessions:
                        print(f"   📦 Архивируем: {session.session_name}")
                        await self._archive_session(session.session_name)
                        await db.delete(session)

                    await db.commit()
                    return len(old_sessions)
                else:
                    print("   ✅ Старых сессий не найдено")
                    return 0

        except Exception as e:
            print(f"   ❌ Ошибка очистки: {e}")
            return 0

    async def _backup_and_remove_session(self, session_file: Path):
        """Создание бэкапа и удаление сессии"""

        session_name = session_file.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"{session_name}_{timestamp}.session.bak"

        try:
            # Создаем бэкап
            shutil.copy2(session_file, backup_file)
            # Удаляем оригинал
            session_file.unlink()
            logger.info(f"📦 Сессия {session_name} заархивирована в {backup_file}")
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа сессии {session_name}: {e}")

    async def _handle_unauthorized_session(self, session_name: str):
        """Обработка неавторизованной сессии"""

        try:
            async with get_db() as db:
                # Обновляем статус в БД
                await db.execute(
                    update(Session)
                    .where(Session.session_name == session_name)
                    .values(status=SessionStatus.BLOCKED)
                )
                await db.commit()

                logger.info(f"🚫 Сессия {session_name} помечена как заблокированная")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса сессии {session_name}: {e}")

    async def _archive_session(self, session_name: str):
        """Архивирование сессии"""

        session_files = list(settings.sessions_dir.rglob(f"{session_name}.session"))

        for session_file in session_files:
            await self._backup_and_remove_session(session_file)

    async def fix_specific_session(self, session_name: str):
        """Исправление конкретной сессии"""

        print(f"🔧 Диагностика сессии: {session_name}")

        # Найдем файл сессии
        session_files = list(settings.sessions_dir.rglob(f"{session_name}.session"))

        if not session_files:
            print(f"   ❌ Файл сессии {session_name} не найден")
            return False

        session_file = session_files[0]

        # Проверяем файл
        print(f"   📁 Файл: {session_file}")
        print(f"   📊 Размер: {session_file.stat().st_size} байт")

        # Проверяем авторизацию
        try:
            from core.integrations.telegram_client import TelegramSessionManager
            session_manager = TelegramSessionManager()
            await session_manager.initialize()

            health_status = await session_manager.health_check()
            is_healthy = health_status.get(session_name, False)

            if is_healthy:
                print(f"   ✅ Сессия авторизована")
            else:
                print(f"   ❌ Сессия НЕ авторизована")
                print(f"   💡 Необходимо:")
                print(f"      1. Удалить файл: {session_file}")
                print(f"      2. Создать новую сессию с тем же номером")
                print(
                    f"      3. Команда: python scripts/session_manager.py create {session_name} +номер_телефона basic_man")

            if hasattr(session_manager, 'disconnect_all'):
                await session_manager.disconnect_all()

            return is_healthy

        except Exception as e:
            print(f"   ❌ Ошибка проверки: {e}")
            return False


async def main():
    """Главная функция"""

    if len(sys.argv) < 2:
        print("🔧 Исправление проблем с сессиями Telegram")
        print()
        print("Использование:")
        print("  python scripts/fix_session_auth.py full                    - полная диагностика")
        print("  python scripts/fix_session_auth.py session <session_name>  - проверка конкретной сессии")
        print("  python scripts/fix_session_auth.py files                   - проверка файлов")
        print("  python scripts/fix_session_auth.py auth                    - проверка авторизации")
        print("  python scripts/fix_session_auth.py cleanup                 - очистка старых сессий")
        return

    command = sys.argv[1]
    fixer = SessionFixer()

    try:
        if command == "full":
            await fixer.run_full_diagnostic()
        elif command == "session" and len(sys.argv) > 2:
            session_name = sys.argv[2]
            await fixer.fix_specific_session(session_name)
        elif command == "files":
            await fixer.check_session_files()
        elif command == "auth":
            await fixer.check_authorization()
        elif command == "cleanup":
            await fixer.cleanup_old_sessions()
        else:
            print(f"❌ Неизвестная команда: {command}")

    except Exception as e:
        print(f"💥 Ошибка выполнения: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Операция прервана")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")