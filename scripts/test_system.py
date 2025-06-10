#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_system_components():
    """Тестирование компонентов системы"""

    print("🧪 Тестирование системы...")

    # Тест 1: База данных
    try:
        from storage.database import db_manager
        await db_manager.initialize()
        health = await db_manager.health_check()
        print(f"🗄️ База данных: {'✅' if health else '❌'}")
        await db_manager.close()
    except Exception as e:
        print(f"🗄️ База данных: ❌ {e}")

    # Тест 2: OpenAI
    try:
        from core.integrations.openai_client import openai_client
        test_result = await openai_client.test_connection()
        print(f"🤖 OpenAI: {'✅' if test_result['success'] else '❌'}")
    except Exception as e:
        print(f"🤖 OpenAI: ❌ {e}")

    # Тест 3: Telegram сессии
    try:
        from core.integrations.telegram_client import telegram_session_manager
        await telegram_session_manager.initialize()
        sessions = await telegram_session_manager.get_active_sessions()
        print(f"📱 Telegram сессии: ✅ ({len(sessions)} активных)")
    except Exception as e:
        print(f"📱 Telegram сессии: ❌ {e}")

    print("\n🎯 Результат тестирования завершен")


if __name__ == "__main__":
    asyncio.run(test_system_components())