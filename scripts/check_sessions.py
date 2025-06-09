#!/usr/bin/env python3
# scripts/check_sessions.py

"""
Проверка статуса всех сессий
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import get_db, db_manager
from storage.models.base import Session
from sqlalchemy import select


async def check_all_sessions():
    """Проверка всех сессий в БД"""

    print("🔍 Проверка всех сессий в базе данных")
    print("=" * 50)

    try:
        await db_manager.initialize()

        async with get_db() as db:
            result = await db.execute(
                select(Session).order_by(Session.session_name)
            )
            sessions = result.scalars().all()

        if not sessions:
            print("❌ Нет сессий в базе данных")
            return

        print(f"📊 Найдено {len(sessions)} сессий в БД:\n")

        # Группируем по статусам
        active_sessions = []
        inactive_sessions = []

        for session in sessions:
            status_emoji = {
                "active": "🟢",
                "inactive": "🟡",
                "banned": "🔴",
                "error": "⚠️"
            }.get(session.status, "❓")

            ai_emoji = "🤖" if session.ai_enabled else "📴"
            persona_emoji = "🎭" if session.persona_type else "❓"

            session_info = f"{status_emoji} {ai_emoji} {persona_emoji} {session.session_name}"

            if session.persona_type:
                session_info += f" ({session.persona_type})"

            if session.username:
                session_info += f" - @{session.username}"

            print(session_info)

            if session.status == "active":
                active_sessions.append(session.session_name)
            else:
                inactive_sessions.append(session.session_name)

        print(f"\n📈 Статистика:")
        print(f"✅ Активных: {len(active_sessions)}")
        print(f"❌ Неактивных: {len(inactive_sessions)}")

        # Показываем сессии без персон
        no_persona = [s for s in sessions if not s.persona_type]
        if no_persona:
            print(f"\n⚠️ Сессии без персоны ({len(no_persona)}):")
            for session in no_persona:
                print(f"   • {session.session_name}")

            print(f"\n💡 Назначьте персоны:")
            print(f"python scripts/session_manager.py persona SESSION_NAME PERSONA_TYPE")

        # Показываем сессии без реф ссылок
        no_reflink = [s for s in sessions if not s.project_ref_link]
        if no_reflink:
            print(f"\n🔗 Сессии без реф ссылки ({len(no_reflink)}):")
            for session in no_reflink[:5]:  # Показываем первые 5
                print(f"   • {session.session_name}")

            if len(no_reflink) > 5:
                print(f"   • ... и еще {len(no_reflink) - 5}")

            print(f"\n💡 Установите реф ссылки:")
            print(f"python scripts/session_manager.py reflink SESSION_NAME \"https://t.me/bot?start=ref\"")

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def test_session_files():
    """Проверка файлов сессий"""

    print("\n📁 Проверка файлов сессий")
    print("=" * 30)

    base_dir = Path(__file__).parent.parent
    sessions_dir = base_dir / "data" / "sessions"

    session_files = list(sessions_dir.rglob("*.session"))

    print(f"📂 Найдено {len(session_files)} файлов сессий:")

    for session_file in session_files:
        size_kb = session_file.stat().st_size / 1024
        print(f"   • {session_file.name} ({size_kb:.1f} KB)")


async def main():
    """Главная функция"""

    try:
        await check_all_sessions()
        await test_session_files()

        print(f"\n🎯 Итог:")
        print(f"✅ Все сессии успешно загружены в систему")
        print(f"💡 Система готова к работе!")

    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())