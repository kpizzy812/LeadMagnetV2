from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import Session, Conversation, SessionStatus
from core.handlers.message_handler import message_handler
from loguru import logger

ai_control_router = Router()

# Глобальный флаг для отключения всей системы ИИ
GLOBAL_AI_ENABLED = True


@ai_control_router.callback_query(F.data == "ai_control_main")
async def ai_control_main(callback: CallbackQuery):
    """Главное меню управления ИИ"""

    try:
        # Получаем статистику
        async with get_db() as db:
            # Всего сессий с включенным ИИ
            enabled_sessions_result = await db.execute(
                select(func.count(Session.id))
                .where(Session.ai_enabled == True)
            )
            enabled_sessions = enabled_sessions_result.scalar() or 0

            # Всего активных диалогов
            active_dialogs_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.status == "active",
                    Conversation.ai_disabled == False
                )
            )
            active_dialogs = active_dialogs_result.scalar() or 0

            # Приостановленных диалогов
            paused_dialogs_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.auto_responses_paused == True)
            )
            paused_dialogs = paused_dialogs_result.scalar() or 0

        global_status = "🟢 Включен" if GLOBAL_AI_ENABLED else "🔴 Отключен"

        text = f"""🤖 <b>Управление системой ИИ</b>

🌐 <b>Глобальный статус:</b> {global_status}

📊 <b>Статистика:</b>
• Сессий с ИИ: {enabled_sessions}
• Активных диалогов: {active_dialogs}
• Приостановленных: {paused_dialogs}

⚙️ <b>Уровни управления:</b>
• 🌐 Глобально - вся система
• 🤖 По сессиям - конкретные аккаунты  
• 💬 По диалогам - отдельные беседы"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔴 Выключить всё" if GLOBAL_AI_ENABLED else "🟢 Включить всё",
                        callback_data="ai_toggle_global"
                    )
                ],
                [
                    InlineKeyboardButton(text="🤖 Управление сессиями", callback_data="ai_sessions_control"),
                    InlineKeyboardButton(text="💬 Управление диалогами", callback_data="ai_dialogs_control")
                ],
                [
                    InlineKeyboardButton(text="⏸️ Пауза всех диалогов", callback_data="ai_pause_all"),
                    InlineKeyboardButton(text="▶️ Возобновить всё", callback_data="ai_resume_all")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="ai_control_main"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню управления ИИ: {e}")
        await callback.answer("❌ Ошибка загрузки")


@ai_control_router.callback_query(F.data == "ai_toggle_global")
async def ai_toggle_global(callback: CallbackQuery):
    """Глобальное включение/отключение ИИ"""

    global GLOBAL_AI_ENABLED
    GLOBAL_AI_ENABLED = not GLOBAL_AI_ENABLED

    status = "включена" if GLOBAL_AI_ENABLED else "отключена"

    if not GLOBAL_AI_ENABLED:
        # Отключаем все сессии
        active_sessions = await message_handler.get_active_sessions()
        for session_name in active_sessions:
            await message_handler.remove_session(session_name)

        await callback.answer(f"🔴 Система ИИ {status}")
    else:
        # Включаем все активные сессии
        async with get_db() as db:
            result = await db.execute(
                select(Session).where(
                    Session.status == SessionStatus.ACTIVE,
                    Session.ai_enabled == True
                )
            )
            sessions = result.scalars().all()

            for session in sessions:
                await message_handler.add_session(session.session_name)

        await callback.answer(f"🟢 Система ИИ {status}")

    # Обновляем меню
    await ai_control_main(callback)


@ai_control_router.callback_query(F.data == "ai_pause_all")
async def ai_pause_all(callback: CallbackQuery):
    """Пауза всех диалогов"""

    try:
        async with get_db() as db:
            # Ставим на паузу все активные диалоги
            await db.execute(
                update(Conversation)
                .where(Conversation.status == "active")
                .values(auto_responses_paused=True)
            )
            await db.commit()

        await callback.answer("⏸️ Все диалоги приостановлены")
        await ai_control_main(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка приостановки диалогов: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_resume_all")
async def ai_resume_all(callback: CallbackQuery):
    """Возобновление всех диалогов"""

    try:
        async with get_db() as db:
            # Убираем паузу со всех диалогов
            await db.execute(
                update(Conversation)
                .values(
                    auto_responses_paused=False,
                    ai_disabled=False
                )
            )
            await db.commit()

        await callback.answer("▶️ Все диалоги возобновлены")
        await ai_control_main(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка возобновления диалогов: {e}")
        await callback.answer("❌ Ошибка")