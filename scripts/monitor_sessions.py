#!/usr/bin/env python3
# scripts/monitor_sessions.py

"""
Мониторинг состояния сессий в реальном времени
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import json

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import db_manager
from core.handlers.message_handler import message_handler
from core.integrations.telegram_client import telegram_session_manager
from loguru import logger


async def monitor_sessions():
    """Мониторинг сессий"""

    print("📊 Мониторинг сессий Lead Management System")
    print("=" * 60)

    try:
        # Инициализируем компоненты
        await db_manager.initialize()
        await telegram_session_manager.initialize()
        await message_handler.initialize()

        # Получаем статистику
        session_stats = await message_handler.get_session_stats()
        realtime_stats = message_handler.get_realtime_stats()
        telegram_health = await telegram_session_manager.health_check()

        print(f"🔄 <b>Общая статистика на {datetime.now().strftime('%H:%M:%S')}</b>")
        print(f"   • Активных сессий: {realtime_stats.get('active_sessions', 0)}")
        print(f"   • Приостановленных: {realtime_stats.get('paused_sessions', 0)}")
        print(f"   • Очередь сообщений: {realtime_stats.get('queue_size', 0)}")
        print(f"   • Задержки ответов: {realtime_stats.get('total_response_delays', 0)}")
        print()

        # Детальная информация по сессиям
        if session_stats:
            print("📋 Детальная информация по сессиям:")
            print("-" * 60)

            for session_name, stats in session_stats.items():
                status = stats.get("status", "unknown")
                status_emoji = {
                    "active": "🟢",
                    "paused": "⏸️",
                    "inactive": "🔴",
                    "disconnected": "⚠️"
                }.get(status, "❓")

                print(f"{status_emoji} {session_name}")
                print(f"   📱 Персона: {stats.get('persona_type', 'не задана')}")
                print(f"   🤖 ИИ: {'включен' if stats.get('ai_enabled') else 'отключен'}")
                print(f"   📊 Статус: {status}")
                print(f"   💬 Активных диалогов: {stats.get('active_dialogs', 0)}")
                print(f"   📨 Сообщений за 24ч: {stats.get('messages_24h', 0)}")
                print(f"   📈 Всего конверсий: {stats.get('total_conversions', 0)}")
                print(f"   🔗 Подключен: {'да' if stats.get('is_connected') else 'нет'}")

                last_activity = stats.get('last_activity')
                if last_activity:
                    print(f"   ⏰ Последняя активность: {last_activity}")
                print()

        # Проверка health check Telegram
        print("📱 Проверка Telegram подключений:")
        print("-" * 40)

        if telegram_health:
            for session_name, is_healthy in telegram_health.items():
                status = "✅ OK" if is_healthy else "❌ Проблема"
                print(f"   {session_name}: {status}")
        else:
            print("   📝 Нет активных подключений")

        print()

        # Рекомендации
        print("💡 Рекомендации:")
        print("-" * 20)

        # Анализируем проблемы
        problems = []

        if realtime_stats.get('active_sessions', 0) == 0:
            problems.append("Нет активных сессий - проверьте авторизацию")

        if realtime_stats.get('queue_size', 0) > 10:
            problems.append(f"Большая очередь сообщений ({realtime_stats['queue_size']}) - система перегружена")

        # Проблемные сессии
        problem_sessions = []
        for session_name, stats in session_stats.items():
            if stats.get('status') == 'disconnected':
                problem_sessions.append(f"{session_name} (отключена)")
            elif not stats.get('is_connected'):
                problem_sessions.append(f"{session_name} (нет подключения)")

        if problem_sessions:
            problems.append(f"Проблемные сессии: {', '.join(problem_sessions)}")

        # Неактивные сессии
        inactive_count = sum(1 for stats in session_stats.values()
                             if stats.get('messages_24h', 0) == 0 and stats.get('status') == 'active')
        if inactive_count > 0:
            problems.append(f"{inactive_count} активных сессий без сообщений за 24ч")

        if problems:
            for problem in problems:
                print(f"   ⚠️ {problem}")
        else:
            print("   ✅ Все системы работают нормально")

        print()

        # Команды для исправления
        if problems:
            print("🔧 Команды для исправления:")
            print("-" * 30)
            print("   python scripts/fix_sessions.py - автоматическое исправление")
            print("   python scripts/session_manager.py check - проверка авторизации")
            print("   python main.py - перезапуск системы")
            print()

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка мониторинга: {e}")


async def monitor_realtime():
    """Мониторинг в реальном времени"""

    print("📊 Мониторинг в реальном времени (Ctrl+C для остановки)")
    print("=" * 60)

    try:
        await db_manager.initialize()
        await message_handler.initialize()

        while True:
            # Очищаем экран (для Unix/Linux/Mac)
            print("\033[2J\033[H", end="")

            # Получаем актуальную статистику
            realtime_stats = message_handler.get_realtime_stats()
            session_stats = await message_handler.get_session_stats()

            print(
                f"🕐 {datetime.now().strftime('%H:%M:%S')} | Активных: {realtime_stats.get('active_sessions', 0)} | Очередь: {realtime_stats.get('queue_size', 0)}")
            print("-" * 60)

            # Показываем топ 5 активных сессий
            sorted_sessions = sorted(
                session_stats.items(),
                key=lambda x: x[1].get('messages_24h', 0),
                reverse=True
            )

            for session_name, stats in sorted_sessions[:5]:
                status = stats.get('status', 'unknown')
                status_emoji = {
                    "active": "🟢",
                    "paused": "⏸️",
                    "inactive": "🔴"
                }.get(status, "❓")

                print(
                    f"{status_emoji} {session_name[:15]:<15} | Диалогов: {stats.get('active_dialogs', 0):>2} | Сообщений: {stats.get('messages_24h', 0):>3}")

            # Ждем 5 секунд
            await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\n\n✅ Мониторинг остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка мониторинга: {e}")
    finally:
        await db_manager.close()


async def export_stats():
    """Экспорт статистики в JSON"""

    try:
        await db_manager.initialize()
        await message_handler.initialize()

        session_stats = await message_handler.get_session_stats()
        realtime_stats = message_handler.get_realtime_stats()

        export_data = {
            "timestamp": datetime.now().isoformat(),
            "realtime_stats": realtime_stats,
            "session_stats": session_stats
        }

        # Сохраняем в файл
        export_file = f"session_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Статистика экспортирована в {export_file}")

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка экспорта: {e}")


async def main():
    """Главная функция"""

    if len(sys.argv) < 2:
        print("📊 Мониторинг сессий Lead Management System")
        print()
        print("Использование:")
        print("  python scripts/monitor_sessions.py status    - состояние сессий")
        print("  python scripts/monitor_sessions.py realtime  - мониторинг в реальном времени")
        print("  python scripts/monitor_sessions.py export    - экспорт статистики в JSON")
        return

    command = sys.argv[1]

    if command == "status":
        await monitor_sessions()
    elif command == "realtime":
        await monitor_realtime()
    elif command == "export":
        await export_stats()
    else:
        print(f"❌ Неизвестная команда: {command}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")