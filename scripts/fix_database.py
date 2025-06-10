#!/usr/bin/env python3
# scripts/fix_database.py - Исправление схемы БД

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import db_manager
from loguru import logger
import sqlalchemy as sa
from sqlalchemy import text


async def fix_database_schema():
    """Исправление схемы базы данных"""

    print("🔧 Исправление схемы базы данных...")

    try:
        await db_manager.initialize()

        # Подключаемся к БД напрямую
        async with db_manager.engine.begin() as conn:
            print("📊 Добавление недостающих колонок в conversations...")

            # Список колонок для добавления
            columns_to_add = [
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_whitelisted BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_blacklisted BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS auto_created BOOLEAN DEFAULT TRUE;",
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_disabled BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS auto_responses_paused BOOLEAN DEFAULT FALSE;"
            ]

            for sql in columns_to_add:
                try:
                    await conn.execute(text(sql))
                    print(f"✅ Добавлена колонка")
                except Exception as e:
                    if "already exists" in str(e):
                        print(f"ℹ️ Колонка уже существует")
                    else:
                        print(f"❌ Ошибка: {e}")

            print("✅ Схема базы данных обновлена")

        await db_manager.close()
        return True

    except Exception as e:
        print(f"❌ Ошибка обновления схемы: {e}")
        return False


async def recreate_tables():
    """Пересоздание всех таблиц (ВНИМАНИЕ: удалит данные!)"""

    print("⚠️ ВНИМАНИЕ: Это удалит ВСЕ данные в базе!")
    confirm = input("Продолжить? (yes/no): ")

    if confirm.lower() not in ['yes', 'y']:
        print("❌ Отменено")
        return False

    try:
        await db_manager.initialize()

        # Импортируем модели
        from storage.models.base import Base

        async with db_manager.engine.begin() as conn:
            print("🗑️ Удаление старых таблиц...")
            await conn.run_sync(Base.metadata.drop_all)

            print("🔨 Создание новых таблиц...")
            await conn.run_sync(Base.metadata.create_all)

        print("✅ Таблицы пересозданы")
        await db_manager.close()
        return True

    except Exception as e:
        print(f"❌ Ошибка пересоздания таблиц: {e}")
        return False


async def main():
    print("🛠️ Исправление базы данных")
    print("=" * 40)
    print("1. Добавить недостающие колонки (безопасно)")
    print("2. Пересоздать таблицы (удалит данные!)")
    print("3. Отмена")

    choice = input("\nВыберите (1-3): ")

    if choice == "1":
        success = await fix_database_schema()
        if success:
            print("\n🎯 Теперь можно запускать систему: python main.py")
    elif choice == "2":
        await recreate_tables()
        print("\n🎯 После пересоздания добавьте сессии заново")
    else:
        print("❌ Отменено")


if __name__ == "__main__":
    asyncio.run(main())