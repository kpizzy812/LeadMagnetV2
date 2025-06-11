# cold_outreach/bot_handlers/lead_handlers.py - ПОЛНАЯ ВЕРСИЯ

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
                        InlineKeyboardButton(text="📝 Создать список", callback_data="leads_create_list")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                    ]
                ]
            )
        else:
            text = f"📚 <b>Все списки лидов ({len(lists_data)})</b>\n\n"

            keyboard_buttons = []

            for lst in lists_data[:10]:  # Показываем первые 10
                status_emoji = "✅" if lst['is_active'] else "❌"
                progress = f"{lst['processed_leads']}/{lst['total_leads']}"

                text += f"{status_emoji} <b>{lst['name']}</b>\n"
                text += f"   • Лидов: {lst['total_leads']}\n"
                text += f"   • Обработано: {progress}\n"
                text += f"   • Создан: {lst['created_at'].strftime('%d.%m.%Y')}\n\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📋 {lst['name'][:25]}...",
                        callback_data=f"leads_view_list_{lst['id']}"
                    )
                ])

            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="📝 Создать список", callback_data="leads_create_list"),
                    InlineKeyboardButton(text="🔍 Дубликаты", callback_data="leads_duplicates")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="leads_view_all"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                ]
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки списков лидов: {e}")
        await callback.answer("❌ Ошибка загрузки списков")


@leads_handlers_router.callback_query(F.data.startswith("leads_view_list_"))
async def leads_view_specific_list(callback: CallbackQuery):
    """Просмотр конкретного списка лидов"""

    try:
        list_id = int(callback.data.split("_")[-1])

        # Получаем статистику списка
        stats = await lead_manager.get_list_stats(list_id)

        if not stats:
            await callback.answer("❌ Список не найден")
            return

        text = f"""📋 <b>{stats['name']}</b>

📝 <b>Описание:</b> {stats['description'] or 'Без описания'}
📊 <b>Источник:</b> {stats['source'] or 'Не указан'}

📈 <b>Статистика:</b>
• Всего лидов: {stats['total_leads']}
• Обработано: {stats['processed_leads']}
• Доступных: {stats['available_leads']}
• Заблокированных: {stats['blocked_leads']}

📞 <b>Контакты:</b>
• Успешных: {stats['successful_contacts']}
• Неудачных: {stats['failed_contacts']}
• Успешность: {stats['success_rate']:.1f}%

📅 <b>Создан:</b> {stats['created_at'].strftime('%d.%m.%Y %H:%M')}"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Добавить лидов",
                        callback_data=f"leads_import_to_{list_id}"
                    ),
                    InlineKeyboardButton(
                        text="🚀 Создать кампанию",
                        callback_data=f"campaigns_create_for_list_{list_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🧹 Очистить",
                        callback_data=f"leads_clean_{list_id}"
                    ),
                    InlineKeyboardButton(
                        text="🗑️ Удалить",
                        callback_data=f"leads_delete_{list_id}"
                    )
                ],
                [
                    InlineKeyboardButton(text="📚 Все списки", callback_data="leads_view_all"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка просмотра списка: {e}")
        await callback.answer("❌ Ошибка загрузки списка")


@leads_handlers_router.callback_query(F.data.startswith("leads_clean_"))
async def leads_clean_list(callback: CallbackQuery):
    """Очистка невалидных лидов из списка"""

    try:
        list_id = int(callback.data.split("_")[-1])

        # Показываем подтверждение
        text = """🧹 <b>Очистка списка лидов</b>

Будут удалены:
• Невалидные username'ы
• Заблокированные лиды
• Дубликаты

Продолжить?"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, очистить",
                        callback_data=f"leads_clean_confirm_{list_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"leads_view_list_{list_id}"
                    )
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка очистки списка: {e}")
        await callback.answer("❌ Ошибка")


@leads_handlers_router.callback_query(F.data.startswith("leads_clean_confirm_"))
async def leads_clean_list_confirm(callback: CallbackQuery):
    """Подтверждение очистки списка"""

    try:
        list_id = int(callback.data.split("_")[-1])

        # Выполняем очистку
        result = await lead_manager.clean_invalid_leads(list_id)

        text = f"""✅ <b>Очистка завершена</b>

📊 <b>Результат:</b>
• Проверено лидов: {result['total_checked']}
• Очищено: {result['cleaned']}

Список обновлен!"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="📋 К списку",
                    callback_data=f"leads_view_list_{list_id}"
                )
            ]]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка подтверждения очистки: {e}")
        await callback.answer("❌ Ошибка очистки")


@leads_handlers_router.callback_query(F.data.startswith("leads_delete_"))
async def leads_delete_list(callback: CallbackQuery):
    """Удаление списка лидов"""

    try:
        list_id = int(callback.data.split("_")[-1])

        text = """🗑️ <b>Удаление списка</b>

⚠️ <b>Внимание!</b> Список будет деактивирован (не удален полностью).

Все связанные кампании также будут остановлены.

Продолжить?"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑️ Да, удалить",
                        callback_data=f"leads_delete_confirm_{list_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"leads_view_list_{list_id}"
                    )
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка удаления списка: {e}")
        await callback.answer("❌ Ошибка")


@leads_handlers_router.callback_query(F.data.startswith("leads_delete_confirm_"))
async def leads_delete_list_confirm(callback: CallbackQuery):
    """Подтверждение удаления списка"""

    try:
        list_id = int(callback.data.split("_")[-1])

        # Удаляем список
        success = await lead_manager.delete_lead_list(list_id)

        if success:
            text = """✅ <b>Список удален</b>

Список деактивирован и больше не будет использоваться в кампаниях."""
        else:
            text = """❌ <b>Ошибка удаления</b>

Не удалось удалить список. Возможно, он используется в активных кампаниях."""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="📚 Все списки", callback_data="leads_view_all")
            ]]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка подтверждения удаления: {e}")
        await callback.answer("❌ Ошибка удаления")


@leads_handlers_router.callback_query(F.data == "leads_duplicates")
async def leads_find_duplicates(callback: CallbackQuery):
    """Поиск дубликатов лидов"""

    try:
        from cold_outreach.leads.duplicate_filter import duplicate_filter

        # Получаем статистику дубликатов
        stats = await duplicate_filter.get_duplicate_stats()
        cross_duplicates = await duplicate_filter.find_cross_list_duplicates()

        text = f"""🔍 <b>Анализ дубликатов</b>

📊 <b>Общая статистика:</b>
• Username'ов в кэше: {stats['total_usernames_in_cache']}
• Списков: {stats['lists_in_cache']}
• Межсписочных дубликатов: {stats['cross_list_duplicates_count']}

🔄 <b>Дубликаты между списками:</b>"""

        if cross_duplicates:
            text += f"\nНайдено {len(cross_duplicates)} дубликатов\n\n"
            for username, info in list(cross_duplicates.items())[:5]:
                text += f"• @{username}: в {info['lists_count']} списках\n"

            if len(cross_duplicates) > 5:
                text += f"\n... и еще {len(cross_duplicates) - 5} дубликатов"
        else:
            text += "\n✅ Межсписочных дубликатов не найдено"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить кэш",
                        callback_data="leads_refresh_cache"
                    )
                ],
                [
                    InlineKeyboardButton(text="📚 Все списки", callback_data="leads_view_all"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка поиска дубликатов: {e}")
        await callback.answer("❌ Ошибка анализа дубликатов")


@leads_handlers_router.callback_query(F.data == "leads_refresh_cache")
async def leads_refresh_cache(callback: CallbackQuery):
    """Обновление кэша дубликатов"""

    try:
        from cold_outreach.leads.duplicate_filter import duplicate_filter

        await callback.answer("⏳ Обновляем кэш...")

        # Обновляем кэш
        await duplicate_filter.refresh_cache()

        text = """✅ <b>Кэш обновлен</b>

Кэш дубликатов полностью перестроен из базы данных.

Теперь анализ дубликатов будет работать с актуальными данными."""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔍 Найти дубликаты", callback_data="leads_duplicates")
            ]]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка обновления кэша: {e}")
        await callback.answer("❌ Ошибка обновления кэша")


@leads_handlers_router.callback_query(F.data == "leads_import")
async def leads_import_general(callback: CallbackQuery):
    """Общий импорт лидов (выбор списка)"""

    try:
        lists_data = await lead_manager.get_all_lists()

        if not lists_data:
            text = """📥 <b>Импорт лидов</b>

❌ У вас нет активных списков для импорта.

Сначала создайте список лидов."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📝 Создать список", callback_data="leads_create_list")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
                    ]
                ]
            )
        else:
            text = """📥 <b>Импорт лидов</b>

Выберите список для добавления лидов:"""

            keyboard_buttons = []
            for lst in lists_data[:10]:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📋 {lst['name']} ({lst['total_leads']} лидов)",
                        callback_data=f"leads_import_to_{lst['id']}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton(text="📝 Создать новый", callback_data="leads_create_list"),
                InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_leads")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка импорта лидов: {e}")
        await callback.answer("❌ Ошибка загрузки")


# Обработчик отмены
@leads_handlers_router.message(lambda message: message.text == "/cancel")
async def cancel_lead_action(message: Message, state: FSMContext):
    """Отмена действия с лидами"""

    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К лидам", callback_data="outreach_leads")
            ]]
        )
    )