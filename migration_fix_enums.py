# migration_fix_enums.py - Скрипт для исправления проблем с enum

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent))

from storage.database import db_manager
from storage.models.base import Base
from sqlalchemy import text
from loguru import logger


async def fix_database_enums():
    """Исправление проблем с enum в базе данных"""

    try:
        logger.info("🔧 Начинаем исправление базы данных...")

        # Инициализируем базу данных
        await db_manager.initialize()

        # Пересоздаем все таблицы с исправленными типами
        async with db_manager.engine.begin() as conn:
            # Удаляем существующие таблицы cold outreach
            await conn.execute(text("DROP TABLE IF EXISTS outreach_messages CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS campaign_session_assignments CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS outreach_campaigns CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS spam_block_records CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS outreach_channel_sources CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS outreach_leads CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS outreach_templates CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS outreach_lead_lists CASCADE"))

            # Удаляем enum типы если они существуют
            try:
                await conn.execute(text("DROP TYPE IF EXISTS campaignstatus CASCADE"))
                await conn.execute(text("DROP TYPE IF EXISTS outreachmessagestatus CASCADE"))
            except:
                pass

            logger.info("✅ Старые таблицы удалены")

            # Создаем таблицы заново с исправленными типами
            await conn.run_sync(Base.metadata.create_all)

            logger.info("✅ Таблицы созданы с исправленными типами")

        logger.success("🎉 База данных успешно исправлена!")

    except Exception as e:
        logger.error(f"❌ Ошибка при исправлении БД: {e}")
        raise
    finally:
        await db_manager.close()


if __name__ == "__main__":
    logger.info("🚀 Запуск миграции базы данных...")
    asyncio.run(fix_database_enums())
    logger.info("✅ Миграция завершена")