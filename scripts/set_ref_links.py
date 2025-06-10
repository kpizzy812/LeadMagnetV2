#!/usr/bin/env python3
# scripts/set_ref_links.py - Установка реферальных ссылок для всех сессий

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import db_manager, get_db
from storage.models.base import Session
from sqlalchemy import select
from loguru import logger


async def set_ref_links():
    """Установка реферальных ссылок для всех сессий"""

    print("🔗 Настройка реферальных ссылок для агентов")
    print("=" * 50)

    # 🎯 ЗДЕСЬ НАСТРАИВАЙТЕ ВАШИ РЕФЕРАЛЬНЫЕ ССЫЛКИ:

    # Вариант 1: Одна ссылка для всех (если у вас один реф код)
    base_ref_link = "https://t.me/your_project_bot?start=ref123"

    # Вариант 2: Уникальные ссылки для каждой сессии (рекомендуется)
    unique_ref_links = {
        "alex_session": "https://t.me/your_project_bot?start=alex001",
        "maria_session": "https://t.me/your_project_bot?start=maria002",
        "max_session": "https://t.me/your_project_bot?start=max003",
        # Добавьте свои сессии и их уникальные коды
    }

    try:
        await db_manager.initialize()

        async with get_db() as db:
            # Получаем все сессии
            result = await db.execute(select(Session))
            sessions = result.scalars().all()

            if not sessions:
                print("❌ Сессии не найдены в базе данных")
                return

            print(f"📋 Найдено {len(sessions)} сессий")

            updated_count = 0

            for session in sessions:
                # Проверяем есть ли уникальная ссылка для этой сессии
                if session.session_name in unique_ref_links:
                    ref_link = unique_ref_links[session.session_name]
                    print(f"🔗 {session.session_name}: уникальная ссылка")
                else:
                    # Используем базовую ссылку
                    ref_link = base_ref_link
                    print(f"🔗 {session.session_name}: базовая ссылка")

                # Обновляем сессию
                session.project_ref_link = ref_link
                updated_count += 1

            await db.commit()

            print(f"\n✅ Обновлено {updated_count} сессий")
            print("🎯 Агенты теперь знают какие ссылки отправлять!")

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def show_current_links():
    """Показать текущие реферальные ссылки"""

    try:
        await db_manager.initialize()

        async with get_db() as db:
            result = await db.execute(select(Session))
            sessions = result.scalars().all()

            print("\n📋 Текущие реферальные ссылки:")
            print("-" * 60)

            for session in sessions:
                ref_link = session.project_ref_link or "❌ НЕ УСТАНОВЛЕНА"
                print(f"🤖 {session.session_name}")
                print(f"   🔗 {ref_link}")
                print()

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        await show_current_links()
    else:
        await set_ref_links()
        await show_current_links()


if __name__ == "__main__":
    print("🎯 Команды:")
    print("python scripts/set_ref_links.py - установить ссылки")
    print("python scripts/set_ref_links.py show - показать текущие")
    print()

    asyncio.run(main())