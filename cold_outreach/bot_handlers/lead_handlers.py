# cold_outreach/bot_handlers/lead_handlers.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from cold_outreach.leads.lead_manager import lead_manager
from loguru import logger

leads_handlers_router = Router()


class LeadStates(StatesGroup):
    """Состояния для создания списков лидов"""
    waiting_list_name = State()
    waiting_list_description = State()
    waiting_leads_data = State()


@leads_handlers_router.callback_query(F.data == "leads_create_list")
async def leads_create_list_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания списка лидов"""

    text = """📋 <b>Создание списка лидов</b>

📝 Введите название для нового списка лидов:

Например: "Telegram каналы крипто", "Instagram блогеры", "Потенциальные инвесторы"

💡 Название поможет вам различать списки в будущем."""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_leads")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(LeadStates.waiting_list_name)


@leads_handlers_router.message(LeadStates.waiting_list_name)
async def leads_create_list_name(message: Message, state: FSMContext):
    """Получение названия списка"""

    list_name = message.text.strip()

    if not list_name or len(list_name) < 3:
        await message.answer("❌ Название должно содержать минимум 3 символа. Попробуйте еще раз:")
        return

    await state.update_data(list_name=list_name)

    text = f"""📋 <b>Создание списка: "{list_name}"</b>

📝 Теперь введите описание (необязательно):

Опишите откуда эти лиды, какая целевая аудитория, особенности и т.д.

Или отправьте "-" чтобы пропустить описание."""

    await message.answer(text)
    await state.set_state(LeadStates.waiting_list_description)


@leads_handlers_router.message(LeadStates.waiting_list_description)
async def leads_create_list_description(message: Message, state: FSMContext):
    """Получение описания списка"""

    description = message.text.strip() if message.text.strip() != "-" else None

    data = await state.get_data()
    list_name = data["list_name"]

    # Создаем список
    try:
        list_id = await lead_manager.create_lead_list(
            name=list_name,
            description=description,
            source="telegram_bot"
        )

        if list_id:
            text = f"""✅ <b>Список создан!</b>

📋 <b>Название:</b> {list_name}
📝 <b>Описание:</b> {description or "Без описания"}
🆔 <b>ID:</b> {list_id}

Теперь вы можете добавить лидов в этот список."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Добавить лидов",
                            callback_data=f"leads_import_to_{list_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(text="📚 Все списки", callback_data="leads_view_all"),
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                    ]
                ]
            )
        else:
            text = "❌ Ошибка создания списка. Попробуйте еще раз."
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                ]]
            )

        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка создания списка лидов: {e}")
        await message.answer("❌ Произошла ошибка при создании списка")

    await state.clear()


@leads_handlers_router.callback_query(F.data.startswith("leads_import_to_"))
async def leads_import_start(callback: CallbackQuery, state: FSMContext):
    """Начало импорта лидов в список"""

    list_id = int(callback.data.split("_")[-1])
    await state.update_data(list_id=list_id)

    text = """📥 <b>Импорт лидов</b>

📝 Вставьте список username'ов пользователей для добавления:

<b>Поддерживаемые форматы:</b>

1️⃣ <b>Простой список:</b>
<code>username1
username2  
@username3
username4</code>

2️⃣ <b>CSV формат:</b>
<code>username,first_name,last_name
user1,Иван,Петров
user2,Мария,Сидорова</code>

⚠️ <b>Важно:</b>
• Каждый username с новой строки
• Символ @ необязателен
• Дубликаты будут автоматически исключены"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_leads")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(LeadStates.waiting_leads_data)


@leads_handlers_router.message(LeadStates.waiting_leads_data)
async def leads_import_data(message: Message, state: FSMContext):
    """Обработка импорта лидов"""

    data = await state.get_data()
    list_id = data["list_id"]
    leads_text = message.text

    if not leads_text or len(leads_text.strip()) < 5:
        await message.answer("❌ Слишком мало данных. Попробуйте еще раз:")
        return

    # Показываем индикатор обработки
    processing_msg = await message.answer("⏳ Обрабатываем лидов...")

    try:
        # Импортируем лидов
        result = await lead_manager.import_leads_from_text(
            list_id=list_id,
            text=leads_text,
            format_type="username_only"  # Пока поддерживаем только простой формат
        )

        # Формируем отчет
        total = result["total_processed"]
        added = result["added"]
        duplicates = result["duplicates"]
        invalid = result["invalid"]
        errors = result["errors"]

        text = f"""📊 <b>Результат импорта</b>

✅ <b>Успешно:</b>
• Обработано: {total}
• Добавлено: {added}

⚠️ <b>Исключено:</b>
• Дубликатов: {duplicates}
• Невалидных: {invalid}
• Ошибок: {errors}

💡 <b>Что дальше?</b>
Теперь вы можете создать кампанию рассылки для этих лидов."""

        # Показываем детали если есть ошибки
        if errors > 0 and len(result["details"]) <= 10:
            text += "\n\n📝 <b>Детали ошибок:</b>\n"
            for detail in result["details"][:5]:  # Показываем первые 5
                if detail["status"] == "error":
                    text += f"• {detail['username']}: {detail['reason']}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚀 Создать кампанию",
                        callback_data=f"campaigns_create_for_list_{list_id}"
                    )
                ],
                [
                    InlineKeyboardButton(text="📚 Все списки", callback_data="leads_view_all"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                ]
            ]
        )

        await processing_msg.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка импорта лидов: {e}")
        await processing_msg.edit_text("❌ Произошла ошибка при импорте лидов")

    await state.clear()


@leads_handlers_router.callback_query(F.data == "leads_view_all")
async def leads_view_all_lists(callback: CallbackQuery):
    """Просмотр всех списков лидов"""

    try:
        lists_data = await lead_manager.get_all_lists()

        if not lists_data:
            text = "📚 <b>Списки лидов</b>\n\n📝 У вас пока нет списков лидов."
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [