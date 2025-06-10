#!/usr/bin/env python3
# scripts/fix_sessions.py

"""
Автоматическое исправление проблем с сессиями
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import db_manager
from core.handlers.message_handler import message_handler
from core.integrations.telegram_client import telegram_session_manager
from loguru import logger
from storage.database import get_db


async def fix_disconnected_sessions():
    """Исправление отключенных сессий"""

    print("🔧 Исправление отключенных сессий...")

    try:
        await message_handler.initialize()

        # Получаем статистику
        session_stats = await message_handler.get_session_stats()

        disconnected_sessions = []
        for session_name, stats in session_stats.items():
            if not stats.get('is_connected') or stats.get('status') == 'disconnected':
                disconnected_sessions.append(session_name)

        if not disconnected_sessions:
            print("   ✅ Все сессии подключены")
            return 0

        print(f"   🔧 Найдено {len(disconnected_sessions)} отключенных сессий")

        fixed_count = 0
        for session_name in disconnected_sessions:
            try:
                # Удаляем и переподключаем
                await message_handler.remove_session(session_name)
                await asyncio.sleep(1)
                await message_handler.add_session(session_name)

                print(f"   ✅ Переподключена сессия: {session_name}")
                fixed_count += 1

            except Exception as e:
                print(f"   ❌ Не удалось исправить {session_name}: {e}")

        print(f"   📊 Исправлено: {fixed_count}/{len(disconnected_sessions)}")
        return fixed_count

    except Exception as e:
        print(f"   ❌ Ошибка исправления отключенных сессий: {e}")
        return 0


async def fix_unauthorized_sessions():
    """Исправление неавторизованных сессий"""

    print("🔑 Проверка авторизации сессий...")

    try:
        await telegram_session_manager.initialize()

        health_check = await telegram_session_manager.health_check()

        unauthorized_sessions = []
        for session_name, is_healthy in health_check.items():
            if not is_healthy:
                unauthorized_sessions.append(session_name)

        if not unauthorized_sessions:
            print("   ✅ Все сессии авторизованы")
            return 0

        print(f"   ⚠️ Найдено {len(unauthorized_sessions)} неавторизованных сессий:")

        for session_name in unauthorized_sessions:
            print(f"   ❌ {session_name} - требует повторной авторизации")

        print("\n   💡 Для исправления:")
        print("   1. Удалите проблемные .session файлы")
        print("   2. Пересоздайте их: python scripts/session_manager.py create <name> <phone>")

        return len(unauthorized_sessions)

    except Exception as e:
        print(f"   ❌ Ошибка проверки авторизации: {e}")
        return 0


async def fix_inactive_sessions():
    """Исправление неактивных сессий"""

    print("😴 Исправление неактивных сессий...")

    try:
        await message_handler.initialize()

        session_stats = await message_handler.get_session_stats()

        inactive_sessions = []
        for session_name, stats in session_stats.items():
            # Сессии активные, но без сообщений за 24ч
            if (stats.get('status') == 'active' and
                    stats.get('messages_24h', 0) == 0 and
                    stats.get('active_dialogs', 0) == 0):
                inactive_sessions.append(session_name)

        if not inactive_sessions:
            print("   ✅ Все активные сессии работают")
            return 0

        print(f"   🔧 Найдено {len(inactive_sessions)} неактивных сессий")

        for session_name in inactive_sessions:
            print(f"   ⚠️ {session_name} - нет активности за 24ч")

        # Предлагаем решения
        print("\n   💡 Возможные причины:")
        print("   • Нет входящих сообщений для обработки")
        print("   • Проблемы с прокси")
        print("   • Аккаунт заблокирован или ограничен")
        print("   • Неправильная настройка персоны")

        return len(inactive_sessions)

    except Exception as e:
        print(f"   ❌ Ошибка проверки неактивных сессий: {e}")
        return 0


async def fix_queue_overflow():
    """Исправление переполнения очереди"""

    print("📬 Проверка очереди сообщений...")

    try:
        await message_handler.initialize()

        realtime_stats = message_handler.get_realtime_stats()
        queue_size = realtime_stats.get('queue_size', 0)

        if queue_size == 0:
            print("   ✅ Очередь сообщений пуста")
            return 0

        if queue_size < 10:
            print(f"   ✅ Очередь в норме: {queue_size} сообщений")
            return 0

        print(f"   ⚠️ Большая очередь: {queue_size} сообщений")

        if queue_size > 50:
            print("   🚨 КРИТИЧЕСКОЕ переполнение очереди!")
            print("   💡 Рекомендации:")
            print("   • Перезапустите систему: python main.py")
            print("   • Проверьте OpenAI API лимиты")
            print("   • Уменьшите количество активных сессий")
        else:
            print("   💡 Система обрабатывает очередь...")

        return queue_size

    except Exception as e:
        print(f"   ❌ Ошибка проверки очереди: {e}")
        return 0


async def cleanup_response_delays():
    """Очистка устаревших задержек ответов"""

    print("⏰ Очистка задержек ответов...")

    try:
        await message_handler.initialize()

        realtime_stats = message_handler.get_realtime_stats()
        delays_count = realtime_stats.get('total_response_delays', 0)

        if delays_count == 0:
            print("   ✅ Нет активных задержек")
            return 0

        print(f"   🔧 Найдено {delays_count} активных задержек")

        # Очищаем устаревшие задержки (старше 1 часа)
        from datetime import timedelta

        current_time = datetime.utcnow()
        old_delays = []

        for key, delay_time in message_handler.response_delays.items():
            if current_time - delay_time > timedelta(hours=1):
                old_delays.append(key)

        # Удаляем устаревшие
        for key in old_delays:
            del message_handler.response_delays[key]

        if old_delays:
            print(f"   ✅ Удалено {len(old_delays)} устаревших задержек")
        else:
            print("   ✅ Все задержки актуальны")

        return len(old_delays)

    except Exception as e:
        print(f"   ❌ Ошибка очистки задержек: {e}")
        return 0


async def fix_database_inconsistencies():
    """Исправление несоответствий в базе данных"""

    print("🗄️ Проверка целостности базы данных...")

    try:
        await db_manager.initialize()

        async with get_db() as db:
            from storage.models.base import Session, Conversation, Message
            from sqlalchemy import select, func, update

            # Проверяем сессии без персон
            result = await db.execute(
                select(func.count(Session.id))
                .where(Session.persona_type.is_(None))
            )
            no_persona_count = result.scalar() or 0

            if no_persona_count > 0:
                print(f"   ⚠️ {no_persona_count} сессий без персон")

                # Автоматически назначаем basic_man
                await db.execute(
                    update(Session)
                    .where(Session.persona_type.is_(None))
                    .values(persona_type="basic_man")
                )
                await db.commit()

                print(f"   ✅ Назначена персона basic_man для {no_persona_count} сессий")
            else:
                print("   ✅ Все сессии имеют персон")

            # Проверяем диалоги с неправильными флагами
            result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.is_whitelisted == True,
                    Conversation.requires_approval == True
                )
            )
            inconsistent_dialogs = result.scalar() or 0

            if inconsistent_dialogs > 0:
                print(f"   🔧 Исправление {inconsistent_dialogs} диалогов с некорректными флагами")

                await db.execute(
                    update(Conversation)
                    .where(
                        Conversation.is_whitelisted == True,
                        Conversation.requires_approval == True
                    )
                    .values(requires_approval=False)
                )
                await db.commit()

                print(f"   ✅ Исправлено {inconsistent_dialogs} диалогов")
            else:
                print("   ✅ Флаги диалогов корректны")

        await db_manager.close()
        return no_persona_count + inconsistent_dialogs

    except Exception as e:
        print(f"   ❌ Ошибка проверки БД: {e}")
        return 0


async def run_full_diagnostic():
    """Полная диагностика и исправление"""

    print("🔍 Запуск полной диагностики системы")
    print("=" * 60)

    total_issues = 0

    # 1. База данных
    total_issues += await fix_database_inconsistencies()

    # 2. Отключенные сессии
    total_issues += await fix_disconnected_sessions()

    # 3. Неавторизованные сессии
    total_issues += await fix_unauthorized_sessions()

    # 4. Неактивные сессии
    total_issues += await fix_inactive_sessions()

    # 5. Очередь сообщений
    queue_issues = await fix_queue_overflow()
    if queue_issues > 10:
        total_issues += 1

    # 6. Задержки ответов
    total_issues += await cleanup_response_delays()

    print("\n" + "=" * 60)
    if total_issues == 0:
        print("✅ Система работает идеально! Проблем не найдено.")
    else:
        print(f"🔧 Диагностика завершена. Найдено и исправлено проблем: {total_issues}")
        print("\n💡 Рекомендации:")

        if queue_issues > 50:
            print("   • Перезапустите систему для сброса очереди")
        if total_issues > 5:
            print("   • Рассмотрите возможность перезапуска всей системы")

        print("   • Мониторьте систему: python scripts/monitor_sessions.py realtime")
        print("   • Повторите диагностику через час")


async def main():
    """Главная функция"""

    if len(sys.argv) < 2:
        print("🔧 Автоматическое исправление проблем с сессиями")
        print()
        print("Доступные команды:")
        print("  python scripts/fix_sessions.py full          - полная диагностика")
        print("  python scripts/fix_sessions.py disconnected  - исправить отключенные")
        print("  python scripts/fix_sessions.py unauthorized  - проверить авторизацию")
        print("  python scripts/fix_sessions.py inactive      - найти неактивные")
        print("  python scripts/fix_sessions.py queue         - проверить очередь")
        print("  python scripts/fix_sessions.py delays        - очистить задержки")
        print("  python scripts/fix_sessions.py database      - проверить БД")
        return

    command = sys.argv[1]

    try:
        if command == "full":
            await run_full_diagnostic()
        elif command == "disconnected":
            await fix_disconnected_sessions()
        elif command == "unauthorized":
            await fix_unauthorized_sessions()
        elif command == "inactive":
            await fix_inactive_sessions()
        elif command == "queue":
            await fix_queue_overflow()
        elif command == "delays":
            await cleanup_response_delays()
        elif command == "database":
            await fix_database_inconsistencies()
        else:
            print(f"❌ Неизвестная команда: {command}")

    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Диагностика прервана")
    except Exception as e:
        print(f"💥 Ошибка запуска: {e}")