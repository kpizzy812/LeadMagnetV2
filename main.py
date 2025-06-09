# main.py

import asyncio
import signal
import sys
from typing import Optional

from loguru import logger
from config.settings.base import settings
from storage.database import db_manager
from core.handlers.message_handler import message_handler
from personas.persona_factory import setup_default_project
from bot.main import bot_manager
from workflows.followups.scheduler import followup_scheduler


class LeadManagementSystem:
    """Главный класс системы управления лидами"""

    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """Инициализация всех компонентов системы"""
        logger.info("🚀 Запуск Lead Management System")

        try:
            # 1. Инициализация базы данных
            logger.info("📊 Инициализация базы данных...")
            await db_manager.initialize()

            # 2. Настройка проекта по умолчанию
            logger.info("🎭 Настройка персон и проектов...")
            setup_default_project()

            # 3. Инициализация обработчика сообщений
            logger.info("📨 Инициализация обработчика сообщений...")
            await message_handler.initialize()

            # 4. Инициализация Telegram бота управления
            logger.info("🤖 Инициализация управляющего бота...")
            await bot_manager.initialize()

            # 5. Инициализация планировщика фолоуапов
            logger.info("📅 Инициализация планировщика фолоуапов...")
            # Запускаем в фоне
            asyncio.create_task(followup_scheduler.start())

            logger.success("✅ Все компоненты инициализированы успешно!")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False

    async def start(self):
        """Запуск системы"""
        if not await self.initialize():
            logger.error("❌ Не удалось инициализировать систему")
            return False

        self.running = True

        # Настройка обработчика сигналов
        self._setup_signal_handlers()

        # Запуск фоновых задач
        tasks = [
            asyncio.create_task(self._main_loop(), name="main_loop"),
            asyncio.create_task(bot_manager.start(), name="bot_manager"),
            asyncio.create_task(self._health_monitor(), name="health_monitor")
        ]

        logger.info("🎯 Lead Management System запущена")

        try:
            # Ждем сигнала завершения
            await self.shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("⚠️ Получен сигнал прерывания")
        finally:
            # Отменяем все задачи
            for task in tasks:
                if not task.done():
                    task.cancel()

            # Ждем завершения задач
            await asyncio.gather(*tasks, return_exceptions=True)

            # Корректное завершение
            await self.shutdown()

        return True

    async def _main_loop(self):
        """Основной цикл системы"""
        while self.running:
            try:
                # Здесь может быть дополнительная логика
                # Например, периодическая проверка статусов, очистка кэшей и т.д.

                await asyncio.sleep(30)  # Цикл каждые 30 секунд

            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                await asyncio.sleep(5)

    async def _health_monitor(self):
        """Мониторинг здоровья системы"""
        while self.running:
            try:
                # Проверяем базу данных
                db_healthy = await db_manager.health_check()
                if not db_healthy:
                    logger.error("❌ Проблемы с базой данных!")

                # Проверяем активные сессии
                active_sessions = await message_handler.get_active_sessions()
                logger.info(f"📊 Активных сессий: {len(active_sessions)}")

                # Проверяем OpenAI
                from core.integrations.openai_client import openai_client
                openai_healthy = await openai_client.health_check()
                if not openai_healthy:
                    logger.error("❌ Проблемы с OpenAI API!")

                await asyncio.sleep(300)  # Проверка каждые 5 минут

            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге: {e}")
                await asyncio.sleep(60)

    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""

        def signal_handler(sig, frame):
            logger.info(f"📡 Получен сигнал {sig}")
            # Устанавливаем событие завершения
            if not self.shutdown_event.is_set():
                self.shutdown_event.set()

        # Обработчики для разных платформ
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)

        logger.info("📡 Обработчики сигналов настроены")

    # И добавить в функцию start() перед try блоком:

    async def start(self):
        """Запуск системы"""
        if not await self.initialize():
            logger.error("❌ Не удалось инициализировать систему")
            return False

        self.running = True

        # Настройка обработчика сигналов
        self._setup_signal_handlers()

        # Запуск фоновых задач
        tasks = []

        try:
            # Создаем задачи
            main_task = asyncio.create_task(self._main_loop(), name="main_loop")
            bot_task = asyncio.create_task(bot_manager.start(), name="bot_manager")
            health_task = asyncio.create_task(self._health_monitor(), name="health_monitor")

            tasks = [main_task, bot_task, health_task]

            logger.info("🎯 Lead Management System запущена")
            logger.info("💡 Для завершения нажмите Ctrl+C")

            # Ждем завершения любой задачи или сигнала
            done, pending = await asyncio.wait(
                tasks + [asyncio.create_task(self.shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )

            logger.info("🛑 Получен сигнал завершения...")

        except KeyboardInterrupt:
            logger.info("⚠️ Получен KeyboardInterrupt")
        except Exception as e:
            logger.error(f"❌ Ошибка в main loop: {e}")
        finally:
            # Отменяем все задачи
            for task in tasks:
                if not task.done():
                    task.cancel()

            # Ждем завершения с таймаутом
            if tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("⏰ Таймаут ожидания завершения задач")

            # Корректное завершение
            await self.shutdown()

        return True

    async def shutdown(self):
        """Корректное завершение работы системы"""
        logger.info("🛑 Завершение работы Lead Management System...")

        self.running = False

        try:
            # Завершаем компоненты в обратном порядке
            logger.info("🤖 Завершение управляющего бота...")
            await bot_manager.shutdown()

            logger.info("📨 Завершение обработчика сообщений...")
            await message_handler.shutdown()

            logger.info("📊 Закрытие базы данных...")
            await db_manager.close()

            # Останавливаем планировщик
            await followup_scheduler.stop()

            logger.success("✅ Lead Management System корректно завершена")

        except Exception as e:
            logger.error(f"❌ Ошибка при завершении: {e}")


async def main():
    """Точка входа в приложение"""
    system = LeadManagementSystem()

    try:
        await system.start()
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        return 1

    return 0


if __name__ == "__main__":
    # Настройка логирования для запуска
    logger.info("🌟 Запуск Lead Management System")
    logger.info(f"🔧 Режим отладки: {settings.system.debug}")
    logger.info(f"📁 Директория данных: {settings.data_dir}")

    # Проверяем наличие .env файла
    env_file = settings.base_dir / ".env"
    if not env_file.exists():
        logger.error("❌ Файл .env не найден! Скопируйте .env.template в .env и заполните")
        sys.exit(1)

    # Запускаем систему
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("⚠️ Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Неожиданная ошибка: {e}")
        sys.exit(1)