# scripts/fix_dialogs.py

# !/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import db_manager, get_db
from storage.models.base import Conversation, Message
from sqlalchemy import select, update
from loguru import logger


async def fix_problematic_dialogs():
    """Исправление проблемных диалогов"""

    print("🔧 Исправление проблемных диалогов...")

    try:
        await db_manager.initialize()

        async with get_db() as db:
            # Находим диалоги с непрочитанными сообщениями пользователей
            result = await db.execute(
                select(Conversation.id, Message.content)
                .join(Message)
                .where(
                    Message.role == "user",
                    Message.processed == False,
                    Conversation.is_whitelisted == True,
                    Conversation.requires_approval == False
                )
            )

            problematic = result.all()

            if problematic:
                print(f"📋 Найдено {len(problematic)} диалогов с необработанными сообщениями")

                # Запускаем обработку
                from core.engine.conversation_manager import conversation_manager

                for conv_id, message_content in problematic:
                    try:
                        response = await conversation_manager.process_user_message(
                            conversation_id=conv_id,
                            message_text=message_content
                        )

                        if response:
                            print(f"✅ Обработан диалог {conv_id}")
                        else:
                            print(f"⚠️ Не удалось обработать диалог {conv_id}")

                    except Exception as e:
                        print(f"❌ Ошибка обработки диалога {conv_id}: {e}")

            else:
                print("✅ Проблемных диалогов не найдено")

        await db_manager.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(fix_problematic_dialogs())