# bot/handlers/sessions.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import Session, SessionStatus, PersonaType
from loguru import logger

sessions_router = Router()


@sessions_router.callback_query(F.data == "sessions_list")
async def sessions_list(callback: CallbackQuery):
    """Список всех сессий"""

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Session)
                .order_by(Session.created_at.desc())
                .limit(20)
            )
            sessions = result.scalars().all()

        if not sessions:
            await callback.message.edit_text(
                "📝 Сессии не найдены",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                    ]]
                )
            )
            return

        text = "👥 <b>Список сессий:</b>\n\n"

        keyboard_buttons = []

        for session in sessions:
            status_emoji = {
                SessionStatus.ACTIVE: "🟢",
                SessionStatus.INACTIVE: "🟡",
                SessionStatus.BANNED: "🔴",
                SessionStatus.ERROR: "⚠️"
            }.get(session.status, "❓")

            ai_status = "🤖" if session.ai_enabled else "📴"

            text += f"{status_emoji} {ai_status} <code>{session.session_name}</code>\n"
            text += f"   • Персона: {session.persona_type or 'не задана'}\n"
            text += f"   • Диалогов: {session.total_conversations}\n"
            text += f"   • Конверсий: {session.total_conversions}\n\n"

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"⚙️ {session.session_name}",
                    callback_data=f"session_manage_{session.id}"
                )
            ])

        # Добавляем кнопки навигации
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data="sessions_list")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка получения списка сессий: {e}")
        await callback.answer("❌ Ошибка загрузки сессий")


@sessions_router.callback_query(F.data.startswith("session_manage_"))
async def session_manage(callback: CallbackQuery):
    """Управление конкретной сессией"""

    try:
        session_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

        if not session:
            await callback.answer("❌ Сессия не найдена")
            return

        status_emoji = {
            SessionStatus.ACTIVE: "🟢 Активна",
            SessionStatus.INACTIVE: "🟡 Неактивна",
            SessionStatus.BANNED: "🔴 Заблокирована",
            SessionStatus.ERROR: "⚠️ Ошибка"
        }.get(session.status, "❓ Неизвестно")

        ai_status = "🤖 Включен" if session.ai_enabled else "📴 Отключен"

        text = f"""⚙️ <b>Управление сессией</b>

📱 <b>Сессия:</b> <code>{session.session_name}</code>
🔐 <b>Telegram ID:</b> <code>{session.telegram_id or 'неизвестен'}</code>
👤 <b>Username:</b> @{session.username or 'неизвестен'}
🎭 <b>Персона:</b> {session.persona_type or 'не задана'}

📊 <b>Статус:</b> {status_emoji}
🤖 <b>ИИ:</b> {ai_status}

📈 <b>Статистика:</b>
• Диалогов: {session.total_conversations}
• Сообщений: {session.total_messages_sent}
• Конверсий: {session.total_conversions}

🔗 <b>Реф ссылка:</b> {session.project_ref_link or 'не задана'}"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🤖 Выкл ИИ" if session.ai_enabled else "🤖 Вкл ИИ",
                        callback_data=f"session_toggle_ai_{session.id}"
                    ),
                    InlineKeyboardButton(
                        text="🎭 Персона",
                        callback_data=f"session_persona_{session.id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="💬 Диалоги",
                        callback_data=f"session_dialogs_{session.id}"
                    ),
                    InlineKeyboardButton(
                        text="📢 Рассылка",
                        callback_data=f"session_broadcast_{session.id}"
                    )
                ],
                [
                    InlineKeyboardButton(text="🔙 К списку", callback_data="sessions_list")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка управления сессией: {e}")
        await callback.answer("❌ Ошибка загрузки сессии")


@sessions_router.callback_query(F.data.startswith("session_toggle_ai_"))
async def session_toggle_ai(callback: CallbackQuery):
    """Переключение ИИ для сессии"""

    try:
        session_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                await callback.answer("❌ Сессия не найдена")
                return

            # Переключаем статус ИИ
            session.ai_enabled = not session.ai_enabled
            await db.commit()

            # Уведомляем обработчик сообщений
            from core.handlers.message_handler import message_handler
            if session.ai_enabled:
                await message_handler.add_session(session.session_name)
            else:
                await message_handler.remove_session(session.session_name)

            status = "включен" if session.ai_enabled else "отключен"
            await callback.answer(f"✅ ИИ для сессии {status}")

            # Обновляем информацию о сессии
            await session_manage(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка переключения ИИ: {e}")
        await callback.answer("❌ Ошибка переключения ИИ")


@sessions_router.callback_query(F.data.startswith("session_persona_"))
async def session_persona_menu(callback: CallbackQuery):
    """Меню выбора персоны для сессии"""

    try:
        session_id = int(callback.data.split("_")[-1])

        text = "🎭 <b>Выберите персону для сессии:</b>\n\n"
        text += "👨 <b>Базовые персоны:</b>\n"
        text += "• <code>basic_man</code> - Простой парень\n"
        text += "• <code>basic_woman</code> - Простая девушка\n\n"
        text += "💼 <b>Продвинутые:</b>\n"
        text += "• <code>hyip_man</code> - HYIP эксперт\n"
        text += "• <code>investor_man</code> - Инвестор\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👨 Простой парень",
                        callback_data=f"session_set_persona_{session_id}_basic_man"
                    ),
                    InlineKeyboardButton(
                        text="👩 Простая девушка",
                        callback_data=f"session_set_persona_{session_id}_basic_woman"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="💼 HYIP мужчина",
                        callback_data=f"session_set_persona_{session_id}_hyip_man"
                    ),
                    InlineKeyboardButton(
                        text="📈 Инвестор",
                        callback_data=f"session_set_persona_{session_id}_investor_man"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад",
                        callback_data=f"session_manage_{session_id}"
                    )
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню персон: {e}")
        await callback.answer("❌ Ошибка загрузки меню")


@sessions_router.callback_query(F.data.startswith("session_set_persona_"))
async def session_set_persona(callback: CallbackQuery):
    """Установка персоны для сессии"""

    try:
        parts = callback.data.split("_")
        session_id = int(parts[3])
        persona_type = parts[4]

        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                await callback.answer("❌ Сессия не найдена")
                return

            # Устанавливаем персону
            session.persona_type = persona_type
            await db.commit()

            persona_names = {
                "basic_man": "Простой парень",
                "basic_woman": "Простая девушка",
                "hyip_man": "HYIP мужчина",
                "investor_man": "Инвестор"
            }

            persona_name = persona_names.get(persona_type, persona_type)
            await callback.answer(f"✅ Установлена персона: {persona_name}")

            # Возвращаемся к управлению сессией
            await session_manage(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка установки персоны: {e}")
        await callback.answer("❌ Ошибка установки персоны")


@sessions_router.callback_query(F.data.startswith("session_dialogs_"))
async def session_dialogs(callback: CallbackQuery):
    """Диалоги конкретной сессии"""

    try:
        session_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            # Получаем сессию
            session_result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = session_result.scalar_one_or_none()

            if not session:
                await callback.answer("❌ Сессия не найдена")
                return

            # Получаем диалоги сессии
            from storage.models.base import Conversation, Lead
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .where(Conversation.session_id == session_id)
                .order_by(Conversation.updated_at.desc())
                .limit(10)
            )
            conversations = result.scalars().all()

        if not conversations:
            text = f"💬 <b>Диалоги сессии {session.session_name}</b>\n\n"
            text += "📝 Диалогов пока нет"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 Назад",
                        callback_data=f"session_manage_{session_id}"
                    )
                ]]
            )
        else:
            text = f"💬 <b>Диалоги сессии {session.session_name}</b>\n\n"

            keyboard_buttons = []

            for conv in conversations:
                status_emoji = "🟢" if conv.status == "active" else "🔴"
                ref_emoji = "🔗" if conv.ref_link_sent else "📝"

                text += f"{status_emoji} {ref_emoji} @{conv.lead.username}\n"
                text += f"   • Этап: {conv.current_stage}\n"
                text += f"   • Сообщений: {conv.messages_count}\n\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"👤 {conv.lead.username}",
                        callback_data=f"dialog_view_{conv.id}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data=f"session_manage_{session_id}"
                )
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки диалогов сессии: {e}")
        await callback.answer("❌ Ошибка загрузки диалогов")