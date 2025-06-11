# main.py - ИСПРАВЛЕННАЯ ВЕРСИЯ с интеграцией Cold Outreach

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

# НОВОЕ: Импорты Cold Outreach системы
from cold_outreach.core.outreach_manager import outreach_manager
from cold_outreach.core.session_controller import session_controller
from cold_outreach.leads.lead_manager import lead_manager
from cold_outreach.templates.template_manager import template_manager
from cold_outreach.safety.rate_limiter import rate_limiter
from cold_outreach.safety.error_handler import error_handler


class LeadManagementSystem:
    """Главный класс системы управления лидами с поддержкой Cold Outreach"""

    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """Инициализация всех компонентов системы"""
        logger.info("🚀 Запуск Lead Management System с Cold Outreach")

        try:
            # 1. Инициализация базы данных
            logger.info("📊 Инициализация базы данных...")
            await db_manager.initialize()

            # 2. Настройка проекта по умолчанию
            logger.info("🎭 Настройка персон и проектов...")
            setup_default_project()

            # 3. НОВОЕ: Инициализация Cold Outreach компонентов
            logger.info("📤 Инициализация Cold Outreach системы...")
            await self._initialize_cold_outreach()

            # 4. Инициализация обработчика сообщений
            logger.info("📨 Инициализация обработчика сообщений...")
            await message_handler.initialize()

            # 5. Инициализация Telegram бота управления
            logger.info("🤖 Инициализация управляющего бота...")
            await bot_manager.initialize()

            # 6. Инициализация планировщика фолоуапов
            logger.info("📅 Инициализация планировщика фолоуапов...")
            # Запускаем в фоне
            asyncio.create_task(followup_scheduler.start())

            logger.success("✅ Все компоненты инициализированы успешно!")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False

    async def _initialize_cold_outreach(self):
        """Инициализация компонентов Cold Outreach"""

        try:
            # Инициализируем в правильном порядке
            logger.info("🔧 Инициализация SessionController...")
            await session_controller.initialize()

            logger.info("📋 Инициализация LeadManager...")
            await lead_manager.initialize()

            logger.info("📝 Инициализация TemplateManager...")
            await template_manager.initialize()

            logger.info("⚡ Инициализация RateLimiter...")
            await rate_limiter.initialize()

            logger.info("🛡️ Инициализация ErrorHandler...")
            # error_handler не требует инициализации, но можем добавить

            logger.info("🎯 Инициализация OutreachManager...")
            await outreach_manager.initialize()

            logger.success("✅ Cold Outreach система инициализирована")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Cold Outreach: {e}")
            raise

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

            # НОВОЕ: Задача мониторинга Cold Outreach
            outreach_task = asyncio.create_task(self._outreach_monitor(), name="outreach_monitor")

            tasks = [main_task, bot_task, health_task, outreach_task]

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
                        timeout=15.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("⏰ Таймаут ожидания завершения задач")

            # Корректное завершение
            await self.shutdown()

        return True

    async def _main_loop(self):
        """Основной цикл системы"""
        while self.running:
            try:
                # НОВОЕ: Периодическая очистка неактивных сессий
                await session_controller.cleanup_inactive_sessions()

                # Очистка кэшей и неактивных соединений
                await message_handler.cleanup_inactive_sessions()

                await asyncio.sleep(300)  # Цикл каждые 5 минут

            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                await asyncio.sleep(30)

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

                # НОВОЕ: Проверяем состояние Cold Outreach
                await self._check_outreach_health()

                await asyncio.sleep(300)  # Проверка каждые 5 минут

            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге: {e}")
                await asyncio.sleep(60)

    async def _outreach_monitor(self):
        """Мониторинг Cold Outreach системы"""
        while self.running:
            try:
                # Получаем статистику активных кампаний
                active_campaigns = await outreach_manager.get_active_campaigns()

                if active_campaigns:
                    logger.info(f"📤 Активных кампаний рассылки: {len(active_campaigns)}")

                # Мониторим режимы сессий
                mode_stats = await session_controller.get_session_mode_stats()
                if mode_stats.get("outreach", 0) > 0:
                    logger.info(f"🔄 Сессий в режиме рассылки: {mode_stats['outreach']}")

                # Мониторим лимиты
                session_stats = await rate_limiter.get_sessions_stats()
                blocked_sessions = sum(1 for stats in session_stats.values()
                                       if not stats.get("can_send", True))

                if blocked_sessions > 0:
                    logger.warning(f"🚫 Заблокированных сессий: {blocked_sessions}")

                await asyncio.sleep(120)  # Мониторинг каждые 2 минуты

            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге outreach: {e}")
                await asyncio.sleep(60)

    async def _check_outreach_health(self):
        """Проверка здоровья Cold Outreach компонентов"""

        try:
            # Проверяем количество активных кампаний
            active_campaigns = await outreach_manager.get_active_campaigns()

            # Проверяем статистику сессий
            session_stats = await outreach_manager.get_session_outreach_stats()

            total_sessions = len(session_stats)
            blocked_sessions = sum(1 for stats in session_stats.values()
                                   if stats.get("is_blocked", False))

            if blocked_sessions > total_sessions * 0.5:  # Если больше 50% заблокированы
                logger.error(f"🚨 Критично: {blocked_sessions}/{total_sessions} сессий заблокированы!")

        except Exception as e:
            logger.error(f"❌ Ошибка проверки здоровья outreach: {e}")

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

    async def shutdown(self):
        """Корректное завершение работы системы"""
        logger.info("🛑 Завершение работы Lead Management System...")

        self.running = False

        try:
            # НОВОЕ: Завершаем Cold Outreach компоненты в правильном порядке
            logger.info("📤 Завершение Cold Outreach системы...")
            await self._shutdown_cold_outreach()

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

    async def _shutdown_cold_outreach(self):
        """Завершение Cold Outreach системы"""

        try:
            # 1. Переводим все сессии в режим ответов с сканированием
            logger.info("🔄 Переключение всех сессий в режим ответов...")
            await session_controller.force_switch_all_to_response(scan_missed=True)

            # 2. Завершаем OutreachManager
            logger.info("🎯 Завершение OutreachManager...")
            await outreach_manager.shutdown()

            # 3. Сохраняем незавершенные данные если нужно
            # (здесь можно добавить логику сохранения состояния)

            logger.info("✅ Cold Outreach система корректно завершена")

        except Exception as e:
            logger.error(f"❌ Ошибка завершения Cold Outreach: {e}")

    # НОВЫЕ методы для управления Cold Outreach из основной системы

    async def emergency_stop_all_outreach(self):
        """Экстренная остановка всех рассылок"""

        try:
            logger.warning("🚨 ЭКСТРЕННАЯ ОСТАНОВКА ВСЕХ РАССЫЛОК")

            # Останавливаем все активные кампании
            active_campaigns = await outreach_manager.get_active_campaigns()

            for campaign in active_campaigns:
                await outreach_manager.stop_campaign(campaign["campaign_id"])

            # Переводим все сессии в режим ответов
            await session_controller.force_switch_all_to_response(scan_missed=True)

            logger.info("✅ Все рассылки экстренно остановлены")

        except Exception as e:
            logger.error(f"❌ Ошибка экстренной остановки: {e}")

    async def get_system_status_with_outreach(self) -> Dict[str, Any]:
        """Получение полного статуса системы включая Cold Outreach"""

        try:
            # Базовый статус системы
            from storage.database import db_manager
            from core.integrations.openai_client import openai_client

            db_status = "✅" if await db_manager.health_check() else "❌"
            openai_status = "✅" if await openai_client.health_check() else "❌"

            active_sessions = await message_handler.get_active_sessions()
            sessions_count = len(active_sessions)

            # НОВОЕ: Статус Cold Outreach
            active_campaigns = await outreach_manager.get_active_campaigns()
            session_stats = await outreach_manager.get_session_outreach_stats()

            outreach_sessions = sum(1 for stats in session_stats.values()
                                    if stats.get("mode") == "outreach")
            blocked_sessions = sum(1 for stats in session_stats.values()
                                   if stats.get("is_blocked", False))

            status_text = f"""📊 <b>Статус системы</b>

🔧 <b>Основные компоненты:</b>
🗄️ База данных: {db_status}
🤖 OpenAI API: {openai_status}
📱 Активных сессий: {sessions_count}

📤 <b>Cold Outreach:</b>
🚀 Активных кампаний: {len(active_campaigns)}
📤 Сессий в рассылке: {outreach_sessions}
🚫 Заблокированных: {blocked_sessions}

🕐 <b>Время проверки:</b> {datetime.now().strftime('%H:%M:%S')}"""

            return {
                "status_text": status_text,
                "components": {
                    "database": db_status == "✅",
                    "openai": openai_status == "✅",
                    "sessions_count": sessions_count,
                    "active_campaigns": len(active_campaigns),
                    "outreach_sessions": outreach_sessions,
                    "blocked_sessions": blocked_sessions
                }
            }

        except Exception as e:
            return {
                "status_text": f"❌ <b>Ошибка получения статуса:</b> {str(e)}",
                "components": {"error": str(e)}
            }


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
    logger.info("🌟 Запуск Lead Management System с Cold Outreach")
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