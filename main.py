# main.py - ОБНОВЛЕННАЯ ВЕРСИЯ для ретроспективной системы

import asyncio
import signal
import sys
from typing import Optional
from datetime import datetime

from loguru import logger
from config.settings.base import settings
from storage.database import db_manager

# Основные компоненты системы
from core.handlers.message_handler import message_handler
from personas.persona_factory import setup_default_project
from bot.main import bot_manager
from workflows.followups.scheduler import followup_scheduler

# Cold Outreach система
from cold_outreach.core.outreach_manager import outreach_manager


class LeadManagementSystem:
    """
    Главный класс системы управления лидами с ретроспективным сканированием.

    Основные изменения:
    - Убраны постоянные обработчики событий
    - Добавлено ретроспективное сканирование раз в N минут
    - Интеграция с cold outreach для приостановки сканирования
    - Упрощенная архитектура без reconnect систем
    """

    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """Инициализация всех компонентов системы"""
        logger.info("🚀 Запуск Lead Management System (ретроспективная версия)")

        try:
            # 1. Инициализация базы данных
            logger.info("📊 Инициализация базы данных...")
            await db_manager.initialize()

            # 2. Создание таблиц для новой системы
            await self._create_retrospective_tables()

            # 3. Настройка проекта по умолчанию
            logger.info("🎭 Настройка персон и проектов...")
            setup_default_project()

            # 4. Инициализация Cold Outreach системы
            if settings.cold_outreach.enabled:
                logger.info("📤 Инициализация Cold Outreach системы...")
                await outreach_manager.initialize()

            # 5. Инициализация упрощенного обработчика сообщений с ретроспективным сканированием
            logger.info("🔍 Инициализация ретроспективного сканирования...")
            await message_handler.initialize()

            # 6. Инициализация Telegram бота управления
            logger.info("🤖 Инициализация управляющего бота...")
            await bot_manager.initialize()

            # 7. Инициализация планировщика фолоуапов
            logger.info("📅 Инициализация планировщика фолоуапов...")
            asyncio.create_task(followup_scheduler.start())

            # 8. Отображение статистики запуска
            await self._show_startup_stats()

            logger.success("✅ Все компоненты инициализированы успешно!")
            logger.info(f"🔍 Ретроспективное сканирование: каждые {settings.system.retrospective_scan_interval} сек")
            logger.info("📋 Система готова к работе!")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации системы: {e}")
            raise

    async def _create_retrospective_tables(self):
        """Создание таблиц для ретроспективной системы"""
        try:
            from storage.models.base import Base
            from storage.database import engine

            # Создаем новые таблицы если их нет
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("✅ Таблицы ретроспективной системы созданы/обновлены")

        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            raise

    async def _show_startup_stats(self):
        """Отображение статистики при запуске"""
        try:
            from storage.database import get_db
            from storage.models.base import Session, Conversation, SessionStatus
            from sqlalchemy import select, func

            async with get_db() as db:
                # Статистика сессий
                sessions_result = await db.execute(
                    select(
                        func.count(Session.id).label('total'),
                        func.count(Session.id).filter(Session.status == SessionStatus.ACTIVE).label('active'),
                        func.count(Session.id).filter(Session.ai_enabled == True).label('ai_enabled')
                    )
                )
                session_stats = sessions_result.first()

                # Статистика диалогов
                conversations_result = await db.execute(
                    select(
                        func.count(Conversation.id).label('total'),
                        func.count(Conversation.id).filter(Conversation.admin_approved == True).label('approved'),
                        func.count(Conversation.id).filter(Conversation.requires_approval == True).label('pending')
                    )
                )
                conv_stats = conversations_result.first()

            logger.info("📊 Статистика системы:")
            logger.info(
                f"   🤖 Сессии: {session_stats.total} всего, {session_stats.active} активных, {session_stats.ai_enabled} с ИИ")
            logger.info(
                f"   💬 Диалоги: {conv_stats.total} всего, {conv_stats.approved} одобренных, {conv_stats.pending} ожидают")

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")

    async def run(self):
        """Запуск системы"""
        try:
            await self.initialize()
            self.running = True

            # Настраиваем обработчики сигналов для graceful shutdown
            for sig in [signal.SIGINT, signal.SIGTERM]:
                signal.signal(sig, lambda s, f: asyncio.create_task(self.shutdown()))

            logger.info("🎯 Система запущена и работает")
            logger.info("💡 Нажмите Ctrl+C для остановки")

            # Запускаем основные задачи
            tasks = [
                asyncio.create_task(bot_manager.run()),
                asyncio.create_task(self._system_monitor()),
                asyncio.create_task(self._wait_for_shutdown())
            ]

            # Ждем завершения любой из задач
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            # Отменяем оставшиеся задачи
            for task in pending:
                task.cancel()

        except KeyboardInterrupt:
            logger.info("🛑 Получен сигнал остановки")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
        finally:
            await self.shutdown()

    async def _system_monitor(self):
        """Мониторинг системы"""
        while self.running:
            try:
                # Проверяем состояние компонентов каждые 5 минут
                await asyncio.sleep(300)

                if not self.running:
                    break

                # Проверяем состояние сканера
                scanner_stats = message_handler.get_realtime_stats()
                if not scanner_stats.get("scanner_running", False):
                    logger.warning("⚠️ Ретроспективный сканер не запущен!")

                # Проверяем состояние БД
                db_healthy = await db_manager.health_check()
                if not db_healthy:
                    logger.error("❌ Проблемы с подключением к базе данных!")

                logger.debug("💓 Мониторинг системы: все компоненты работают")

            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга системы: {e}")
                await asyncio.sleep(60)

    async def _wait_for_shutdown(self):
        """Ожидание сигнала завершения"""
        await self.shutdown_event.wait()

    async def shutdown(self):
        """Корректное завершение работы системы"""
        if not self.running:
            return

        logger.info("🛑 Начинаем корректное завершение системы...")
        self.running = False
        self.shutdown_event.set()

        try:
            # 1. Останавливаем планировщик фолоуапов
            logger.info("📅 Остановка планировщика фолоуапов...")
            await followup_scheduler.stop()

            # 2. Останавливаем message_handler (и ретроспективный сканер)
            logger.info("🔍 Остановка ретроспективного сканирования...")
            await message_handler.shutdown()

            # 3. Останавливаем Cold Outreach
            if settings.cold_outreach.enabled:
                logger.info("📤 Остановка Cold Outreach системы...")
                await outreach_manager.shutdown()

            # 4. Останавливаем Telegram бота
            logger.info("🤖 Остановка управляющего бота...")
            await bot_manager.shutdown()

            # 5. Закрываем подключение к БД
            logger.info("📊 Закрытие подключения к базе данных...")
            await db_manager.close()

            logger.success("✅ Система корректно завершена")

        except Exception as e:
            logger.error(f"❌ Ошибка при завершении системы: {e}")

    async def get_system_status(self) -> dict:
        """Получение статуса системы"""
        try:
            stats = await message_handler.get_realtime_stats()

            # Добавляем информацию о cold outreach
            if settings.cold_outreach.enabled:
                co_stats = await outreach_manager.get_status()
                stats["cold_outreach"] = co_stats

            stats.update({
                "system_version": "2.0_retrospective",
                "running": self.running,
                "startup_time": datetime.utcnow().isoformat(),
                "scan_interval": settings.system.retrospective_scan_interval
            })

            return stats

        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса системы: {e}")
            return {"error": str(e)}


async def main():
    """Главная функция"""
    # Настройка логирования
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.system.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True
    )

    # Логирование в файл
    logger.add(
        settings.logs_dir / "system.log",
        level="INFO",
        rotation="1 day",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )

    # Логирование ошибок отдельно
    logger.add(
        settings.logs_dir / "errors.log",
        level="ERROR",
        rotation="1 day",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )

    logger.info("🎯 Lead Management System v2.0 (Retrospective)")
    logger.info("=" * 60)

    # Проверяем настройки
    if settings.system.retrospective_scan_interval < 60:
        logger.warning("⚠️ Интервал сканирования меньше 60 секунд - может быть слишком частым")

    # Создаем и запускаем систему
    system = LeadManagementSystem()
    await system.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 До свидания!")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка запуска: {e}")
        sys.exit(1)