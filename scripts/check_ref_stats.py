#!/usr/bin/env python3
# scripts/check_ref_stats.py - Статистика по реферальным ссылкам

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import db_manager, get_db
from storage.models.base import Session, Conversation, Lead
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload


async def ref_links_stats():
    """Статистика по реферальным ссылкам"""

    print("📊 Статистика реферальных ссылок")
    print("=" * 50)

    try:
        await db_manager.initialize()

        async with get_db() as db:
            # Статистика по сессиям
            result = await db.execute(
                select(Session)
                .options(selectinload(Session.conversations))
            )
            sessions = result.scalars().all()

            total_conversations = 0
            total_ref_sent = 0

            print("📋 Статистика по агентам:")
            print("-" * 60)

            for session in sessions:
                # Подсчитываем диалоги где отправлена реф ссылка
                ref_sent_count = sum(1 for conv in session.conversations if conv.ref_link_sent)
                total_conversations += len(session.conversations)
                total_ref_sent += ref_sent_count

                conversion_rate = (ref_sent_count / max(len(session.conversations), 1)) * 100

                print(f"🤖 {session.session_name}")
                print(f"   📱 Персона: {session.persona_type or 'не задана'}")
                print(f"   💬 Всего диалогов: {len(session.conversations)}")
                print(f"   🔗 Реф ссылок отправлено: {ref_sent_count}")
                print(f"   📈 Конверсия: {conversion_rate:.1f}%")

                if session.project_ref_link:
                    print(f"   🌐 Ссылка: {session.project_ref_link[:50]}...")
                else:
                    print(f"   ❌ Ссылка: НЕ УСТАНОВЛЕНА")
                print()

            # Общая статистика
            overall_conversion = (total_ref_sent / max(total_conversations, 1)) * 100

            print("🎯 ОБЩАЯ СТАТИСТИКА:")
            print(f"   📊 Всего диалогов: {total_conversations}")
            print(f"   🔗 Реф ссылок отправлено: {total_ref_sent}")
            print(f"   📈 Общая конверсия: {overall_conversion:.1f}%")

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def recent_conversions():
    """Последние конверсии (отправленные ссылки)"""

    print("\n🎯 Последние отправленные реферальные ссылки:")
    print("-" * 60)

    try:
        await db_manager.initialize()

        async with get_db() as db:
            # Последние 10 диалогов где отправлена реф ссылка
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(Conversation.ref_link_sent == True)
                .order_by(Conversation.ref_link_sent_at.desc())
                .limit(10)
            )
            conversations = result.scalars().all()

            if not conversations:
                print("📝 Пока нет отправленных реферальных ссылок")
                return

            for conv in conversations:
                time_ago = datetime.now() - conv.ref_link_sent_at if conv.ref_link_sent_at else timedelta(0)
                hours_ago = int(time_ago.total_seconds() / 3600)

                print(f"✅ @{conv.lead.username} ← {conv.session.session_name}")
                print(f"   ⏰ {hours_ago}ч назад")
                print(f"   📊 Этап: {conv.current_stage}")
                print()

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def main():
    await ref_links_stats()
    await recent_conversions()

    print("\n💡 Советы по улучшению конверсии:")
    print("• Убедитесь что у всех сессий установлены уникальные реф ссылки")
    print("• Сессии без персон показывают худшую конверсию")
    print("• Регулярно проверяйте что агенты отправляют ссылки")
    print("• Анализируйте на каких этапах воронки теряются лиды")


if __name__ == "__main__":
    asyncio.run(main())