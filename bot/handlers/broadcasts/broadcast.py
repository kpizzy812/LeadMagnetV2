# bot/handlers/broadcasts.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import Session, Conversation, Lead
from loguru import logger


broadcasts_router = Router()


@broadcasts_router.callback_query(F.data == "broadcast_main")
async def broadcast_main(callback: CallbackQuery):
    """Главное меню рассылок"""

    text = """📢 <b>Система рассылок</b>

Выберите тип рассылки:

🎯 <b>По всем лидам</b> - отправка всем лидам во всех сессиях
👥 <b>По сессии</b> - рассылка через конкретную сессию
🔗 <b>По статусу</b> - лидам с/без реф ссылки
🎭 <b>По персоне</b> - лидам определенных персон

⚠️ <b>Внимание:</b> Рассылки выполняются с задержками для безопасности"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 Всем лидам", callback_data="broadcast_all"),
                InlineKeyboardButton(text="👥 По сессии", callback_data="broadcast_session")
            ],
            [
                InlineKeyboardButton(text="🔗 По статусу", callback_data="broadcast_status"),
                InlineKeyboardButton(text="🎭 По персоне", callback_data="broadcast_persona")
            ],
            [
                InlineKeyboardButton(text="📊 История", callback_data="broadcast_history"),
                InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@broadcasts_router.callback_query(F.data == "broadcast_session")
async def broadcast_session_list(callback: CallbackQuery):
    """Выбор сессии для рассылки"""

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Session)
                .where(Session.status == 'active')
                .order_by(Session.session_name)
            )
            sessions = result.scalars().all()

        if not sessions:
            await callback.answer("❌ Нет активных сессий")
            return

        text = "👥 <b>Выберите сессию для рассылки:</b>\n\n"

        keyboard_buttons = []

        for session in sessions:
            text += f"🤖 <code>{session.session_name}</code>\n"
            text += f"   • Персона: {session.persona_type or 'не задана'}\n"
            text += f"   • Диалогов: {session.total_conversations}\n\n"

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📤 {session.session_name}",
                    callback_data=f"broadcast_session_select_{session.id}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_main")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки сессий для рассылки: {e}")
        await callback.answer("❌ Ошибка загрузки сессий")


@broadcasts_router.callback_query(F.data.startswith("broadcast_session_select_"))
async def broadcast_session_select(callback: CallbackQuery):
    """Настройка рассылки для выбранной сессии"""

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

            # Статистика по диалогам сессии
            total_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.session_id == session_id)
            )
            total_dialogs = total_result.scalar() or 0

            with_ref_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.session_id == session_id,
                    Conversation.ref_link_sent == True
                )
            )
            with_ref = with_ref_result.scalar() or 0

            without_ref = total_dialogs - with_ref

        text = f"""📤 <b>Рассылка через {session.session_name}</b>

🎭 <b>Персона:</b> {session.persona_type or 'не задана'}

📊 <b>Целевая аудитория:</b>
• Всего диалогов: {total_dialogs}
• С реф ссылкой: {with_ref}
• Без реф ссылки: {without_ref}

Выберите целевую группу:"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🎯 Всем ({total_dialogs})",
                        callback_data=f"broadcast_prepare_{session_id}_all"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"🔗 С реф ссылкой ({with_ref})",
                        callback_data=f"broadcast_prepare_{session_id}_with_ref"
                    ),
                    InlineKeyboardButton(
                        text=f"📝 Без реф ссылки ({without_ref})",
                        callback_data=f"broadcast_prepare_{session_id}_without_ref"
                    )
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_session")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка выбора сессии для рассылки: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@broadcasts_router.callback_query(F.data.startswith("broadcast_prepare_"))
async def broadcast_prepare(callback: CallbackQuery):
    """Подготовка к рассылке - запрос текста сообщения"""

    # Парсим параметры
    parts = callback.data.split("_")
    session_id = int(parts[2])
    target_type = parts[3]

    # Сохраняем параметры рассылки в состояние (в реальном проекте лучше использовать FSM)
    # Пока что просто покажем заглушку

    text = f"""✏️ <b>Подготовка рассылки</b>

📤 <b>Параметры:</b>
• Сессия ID: {session_id}
• Цель: {target_type}

🚧 <b>Функция в разработке</b>

Для реализации нужно:
1. Добавить FSM (Finite State Machine) для ввода текста
2. Поддержку медиа файлов
3. Предпросмотр сообщения
4. Подтверждение рассылки
5. Мониторинг выполнения"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_session")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@broadcasts_router.callback_query(F.data == "broadcast_status")
async def broadcast_status(callback: CallbackQuery):
    """Рассылка по статусу реф ссылки"""

    try:
        async with get_db() as db:
            from sqlalchemy import func

            # Статистика по статусам
            with_ref_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.ref_link_sent == True)
            )
            with_ref = with_ref_result.scalar() or 0

            without_ref_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.ref_link_sent == False)
            )
            without_ref = without_ref_result.scalar() or 0

        text = f"""🔗 <b>Рассылка по статусу реф ссылки</b>

📊 <b>Распределение лидов:</b>
• С отправленной ссылкой: {with_ref}
• Без отправленной ссылки: {without_ref}

Выберите целевую группу:"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🔗 С ссылкой ({with_ref})",
                        callback_data="broadcast_status_with_ref"
                    ),
                    InlineKeyboardButton(
                        text=f"📝 Без ссылки ({without_ref})",
                        callback_data="broadcast_status_without_ref"
                    )
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка рассылки по статусу: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@broadcasts_router.callback_query(F.data == "broadcast_history")
async def broadcast_history(callback: CallbackQuery):
    """История рассылок"""

    text = """📊 <b>История рассылок</b>

🚧 <b>Функция в разработке</b>

Здесь будет отображаться:
• Список выполненных рассылок
• Статистика доставки
• Результаты по конверсиям
• Ошибки доставки"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_main")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)