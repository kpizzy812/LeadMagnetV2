# bot/middlewares/auth.py

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from config.settings.base import settings
from loguru import logger


class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации админов"""

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message | CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id

        # Проверяем, что пользователь является админом
        if user_id not in settings.telegram.admin_ids:
            logger.warning(f"🚫 Неавторизованный доступ от пользователя {user_id}")

            if isinstance(event, Message):
                await event.answer("❌ У вас нет доступа к этому боту.")
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ У вас нет доступа к этому боту.", show_alert=True)

            return

        # Логируем действие админа
        action = "message" if isinstance(event, Message) else "callback"
        logger.info(f"👤 Админ {user_id}: {action}")

        # Продолжаем обработку
        return await handler(event, data)