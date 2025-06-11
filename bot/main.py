# bot/main.py

import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config.settings.base import settings
from bot.middlewares.auth import AuthMiddleware
from bot.handlers.dashboard.dashboard import dashboard_router
from bot.handlers.sessions.sessions import sessions_router
from bot.handlers.dialogs.dialogs import dialogs_router
from bot.handlers.analytics.analytics import analytics_router
from bot.handlers.broadcasts.broadcast import broadcasts_router
from bot.handlers.followups.followups import followups_router
from bot.handlers.ai_control.ai_control import ai_control_router
from loguru import logger

from cold_outreach.bot_handlers.main_menu import outreach_router
from cold_outreach.core.outreach_manager import outreach_manager
from cold_outreach.campaigns.campaign_manager import campaign_manager
from cold_outreach.templates.template_manager import template_manager
from cold_outreach.leads.lead_manager import lead_manager
from cold_outreach.bot_handlers.campaign_handlers import campaign_handlers_router

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
            self.dp.include_router(followups_router)
            self.dp.include_router(ai_control_router)

            # НОВОЕ: Регистрируем роутер Cold Outreach
            self.dp.include_router(outreach_router)
            outreach_router.include_router(campaign_handlers_router)


            await outreach_manager.initialize()
            await campaign_manager.initialize()
            await template_manager.initialize()
            await lead_manager.initialize()

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
            # Уведомляем админов о запуске
            await self.notify_admins_startup()

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
                # НОВОЕ: Завершаем OutreachManager
                await outreach_manager.shutdown()
                # Уведомляем админов о завершении
                await self.notify_admins_shutdown()

                await self.bot.session.close()
                logger.info("🤖 Управляющий бот остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки бота: {e}")

    async def notify_admins_startup(self):
        """Уведомление админов о запуске системы"""

        startup_message = """🚀 <b>Lead Management System запущена!</b>

✅ Все компоненты инициализированы
🤖 Управляющий бот готов к работе
📊 База данных подключена
🎭 Персоны загружены

Доступные команды: /start"""

        for admin_id in settings.telegram.admin_ids:
            try:
                await self.bot.send_message(admin_id, startup_message)
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомления админу {admin_id}: {e}")

    async def notify_admins_shutdown(self):
        """Уведомление админов о завершении работы"""

        shutdown_message = """🛑 <b>Lead Management System завершает работу</b>

Все компоненты корректно останавливаются...
До встречи! 👋"""

        for admin_id in settings.telegram.admin_ids:
            try:
                await self.bot.send_message(admin_id, shutdown_message)
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомления админу {admin_id}: {e}")

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

    async def notify_new_lead(self, session_name: str, lead_username: str):
        """Уведомление о новом лиде"""

        message = f"""🆕 <b>Новый лид!</b>

👤 <b>Лид:</b> @{lead_username}
🤖 <b>Сессия:</b> {session_name}
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}

Система начала обработку диалога."""

        # ИСПРАВЛЕНИЕ: Используем простой callback без сложной логики
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="💬 Открыть диалоги",
                    callback_data="dialogs_list"
                )
            ]]
        )

        await self.broadcast_to_admins(message, keyboard)

    async def notify_conversion(self, session_name: str, lead_username: str):
        """Уведомление о конверсии"""

        message = f"""🎯 <b>Конверсия!</b>

✅ <b>Лид:</b> @{lead_username}
🤖 <b>Сессия:</b> {session_name}
🔗 <b>Реф ссылка отправлена!</b>
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}

Отличная работа! 🎉"""

        await self.broadcast_to_admins(message)

    async def notify_error(self, error_type: str, details: str):
        """Уведомление об ошибке"""

        message = f"""⚠️ <b>Ошибка системы</b>

🔍 <b>Тип:</b> {error_type}
📝 <b>Детали:</b> {details}
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}

Проверьте логи для подробностей."""

        await self.broadcast_to_admins(message)

    async def get_system_status(self) -> str:
        """Получение статуса системы для админов"""

        try:
            from storage.database import db_manager
            from core.handlers.message_handler import message_handler
            from core.integrations.openai_client import openai_client

            # Проверяем компоненты
            db_status = "✅" if await db_manager.health_check() else "❌"
            openai_status = "✅" if await openai_client.health_check() else "❌"

            active_sessions = await message_handler.get_active_sessions()
            sessions_count = len(active_sessions)

            status_text = f"""📊 <b>Статус системы</b>

🗄️ <b>База данных:</b> {db_status}
🤖 <b>OpenAI API:</b> {openai_status}
📱 <b>Активных сессий:</b> {sessions_count}

🕐 <b>Время проверки:</b> {datetime.now().strftime('%H:%M:%S')}"""

            return status_text

        except Exception as e:
            return f"❌ <b>Ошибка получения статуса:</b> {str(e)}"


# Глобальный экземпляр менеджера бота
bot_manager = BotManager()