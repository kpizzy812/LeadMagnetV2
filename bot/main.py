# bot/main.py

import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

from config.settings.base import settings
from bot.middlewares.auth import AuthMiddleware
from bot.handlers.dashboard import dashboard_router
from bot.handlers.sessions import sessions_router
from bot.handlers.dialogs import dialogs_router
from bot.handlers.analytics import analytics_router
from bot.handlers.broadcasts import broadcasts_router
from loguru import logger


class BotManager:
    """Менеджер управляющего Telegram бота"""

    def __init__(self):
        self.bot: Bot = None
        self.dp: Dispatcher = None
        self.running = False

    async def initialize(self):
        """Инициализация бота"""
        try:
            # Создаем бота
            self.bot = Bot(
                token=settings.telegram.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                session=AiohttpSession()
            )

            # Создаем диспетчер
            self.dp = Dispatcher()

            # Регистрируем middleware
            self.dp.message.middleware(AuthMiddleware())
            self.dp.callback_query.middleware(AuthMiddleware())

            # Регистрируем роутеры
            self.dp.include_router(dashboard_router)
            self.dp.include_router(sessions_router)
            self.dp.include_router(dialogs_router)
            self.dp.include_router(analytics_router)
            self.dp.include_router(broadcasts_router)

            # Проверяем соединение
            bot_info = await self.bot.get_me()
            logger.info(f"🤖 Управляющий бот инициализирован: @{bot_info.username}")

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации бота: {e}")
            return False

    async def start(self):
        """Запуск бота"""
        if not self.bot or not self.dp:
            logger.error("❌ Бот не инициализирован")
            return

        self.running = True

        try:
            # Запускаем бота
            logger.info("🚀 Запуск управляющего бота...")
            await self.dp.start_polling(self.bot)

        except Exception as e:
            logger.error(f"❌ Ошибка при работе бота: {e}")
        finally:
            self.running = False

    async def shutdown(self):
        """Завершение работы бота"""
        if self.running and self.bot:
            try:
                await self.bot.session.close()
                logger.info("🤖 Управляющий бот остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки бота: {e}")

    async def send_notification(self, admin_id: int, message: str, reply_markup=None):
        """Отправка уведомления админу"""
        try:
            await self.bot.send_message(
                chat_id=admin_id,
                text=message,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления {admin_id}: {e}")

    async def broadcast_to_admins(self, message: str, reply_markup=None):
        """Рассылка всем админам"""
        for admin_id in settings.telegram.admin_ids:
            await self.send_notification(admin_id, message, reply_markup)


# Глобальный экземпляр менеджера бота
bot_manager = BotManager()