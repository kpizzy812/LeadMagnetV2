# cold_outreach/bot_handlers/template_handlers.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from cold_outreach.templates.template_manager import template_manager
from loguru import logger

template_handlers_router = Router()


class TemplateStates(StatesGroup):
    """Состояния для создания шаблонов"""
    waiting_name = State()
    waiting_description = State()
    waiting_text = State()
    waiting_category = State()


@template_handlers_router.callback_query(F.data == "templates_create")
async def templates_create_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания шаблона"""

    text = """📝 <b>Создание шаблона сообщения</b>

📝 Введите название шаблона:

Например: "Знакомство с криптопроектом", "Приглашение в инвестицию", "Презентация возможностей"

💡 Название поможет быстро найти шаблон при создании кампаний."""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_templates")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(TemplateStates.waiting_name)


@template_handlers_router.message(TemplateStates.waiting_name)
async def templates_create_name(message: Message, state: FSMContext):
    """Получение названия шаблона"""

    template_name = message.text.strip()

    if not template_name or len(template_name) < 3:
        await message.answer("❌ Название должно содержать минимум 3 символа. Попробуйте еще раз:")
        return

    await state.update_data(template_name=template_name)

    text = f"""📝 <b>Шаблон: "{template_name}"</b>

📝 Введите описание шаблона (необязательно):

Опишите для какой аудитории предназначен, особенности, цель и т.д.

Или отправьте "-" чтобы пропустить описание."""

    await message.answer(text)
    await state.set_state(TemplateStates.waiting_description)


@template_handlers_router.message(TemplateStates.waiting_description)
async def templates_create_description(message: Message, state: FSMContext):
    """Получение описания шаблона"""

    description = message.text.strip() if message.text.strip() != "-" else None
    await state.update_data(description=description)

    text = """📝 <b>Текст сообщения</b>

Введите текст шаблона сообщения:

<b>💡 Доступные переменные:</b>
• <code>{username}</code> - имя пользователя
• <code>{first_name}</code> - имя
• <code>{full_name}</code> - полное имя
• <code>{date}</code> - текущая дата
• <code>{random_greeting}</code> - случайное приветствие
• <code>{random_emoji}</code> - случайный emoji

<b>📝 Пример:</b>
<code>Привет, {username}! 👋

Увидел твой профиль и подумал - может быть интересна тема пассивного дохода от криптовалют?

Сам недавно начал использовать ИИ-бота для торговли, результаты впечатляют 📈

Если интересно - могу показать как это работает</code>"""

    await message.answer(text)
    await state.set_state(TemplateStates.waiting_text)


@template_handlers_router.message(TemplateStates.waiting_text)
async def templates_create_text(message: Message, state: FSMContext):
    """Получение текста шаблона"""

    template_text = message.text.strip()

    if not template_text or len(template_text) < 10:
        await message.answer("❌ Текст слишком короткий (минимум 10 символов). Попробуйте еще раз:")
        return

    # Валидируем шаблон
    validation = await template_manager.validate_template(template_text)

    if not validation["valid"]:
        error_text = "❌ <b>Ошибки в шаблоне:</b>\n"
        for error in validation["errors"]:
            error_text += f"• {error}\n"

        await message.answer(error_text)
        return

    await state.update_data(template_text=template_text)

    # Показываем предупреждения если есть
    warnings_text = ""
    if validation["warnings"]:
        warnings_text = "\n⚠️ <b>Предупреждения:</b>\n"
        for warning in validation["warnings"]:
            warnings_text += f"• {warning}\n"

    data = await state.get_data()

    text = f"""📝 <b>Предпросмотр шаблона</b>

📋 <b>Название:</b> {data['template_name']}
📝 <b>Описание:</b> {data['description'] or 'Без описания'}

💬 <b>Текст:</b>
<pre>{template_text}</pre>

📊 <b>Статистика:</b>
• Длина: {validation['length']} символов
• Переменных: {len(validation['variables'])}
• Переменные: {', '.join(validation['variables']) if validation['variables'] else 'Нет'}

{warnings_text}

Выберите категорию для шаблона:"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 Знакомство", callback_data="template_cat_introduction"),
                InlineKeyboardButton(text="💼 Бизнес", callback_data="template_cat_business")
            ],
            [
                InlineKeyboardButton(text="📈 Инвестиции", callback_data="template_cat_investment"),
                InlineKeyboardButton(text="🔥 HYIP", callback_data="template_cat_hyip")
            ],
            [
                InlineKeyboardButton(text="📝 Общий", callback_data="template_cat_general"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_templates")
            ]
        ]
    )

    await message.answer(text, reply_markup=keyboard)
    await state.set_state(TemplateStates.waiting_category)


@template_handlers_router.callback_query(F.data.startswith("template_cat_"), TemplateStates.waiting_category)
async def templates_create_category(callback: CallbackQuery, state: FSMContext):
    """Выбор категории и создание шаблона"""

    category = callback.data.replace("template_cat_", "")

    data = await state.get_data()

    # Создаем шаблон
    try:
        template_id = await template_manager.create_template(
            name=data["template_name"],
            text=data["template_text"],
            description=data["description"],
            category=category,
            created_by="telegram_bot"
        )

        if template_id:
            # Тестируем шаблон
            preview = await template_manager.preview_substitution(
                data["template_text"],
                {"username": "example_user", "first_name": "Иван"}
            )

            text = f"""✅ <b>Шаблон создан!</b>

📋 <b>Название:</b> {data['template_name']}
🏷️ <b>Категория:</b> {category}
🆔 <b>ID:</b> {template_id}

📱 <b>Предпросмотр с переменными:</b>
<pre>{preview}</pre>

Теперь вы можете использовать этот шаблон в кампаниях рассылки."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🚀 Создать кампанию",
                            callback_data=f"campaigns_create_with_template_{template_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(text="📚 Все шаблоны", callback_data="templates_view_all"),
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_templates")
                    ]
                ]
            )
        else:
            text = "❌ Ошибка создания шаблона. Попробуйте еще раз."
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_templates")
                ]]
            )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка создания шаблона: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при создании шаблона")

    await state.clear()


@template_handlers_router.callback_query(F.data == "templates_view_all")
async def templates_view_all(callback: CallbackQuery):
    """Просмотр всех шаблонов"""

    try:
        templates_list = await template_manager.get_templates_list(limit=15)

        if not templates_list:
            text = "📝 <b>Шаблоны сообщений</b>\n\n📝 У вас пока нет шаблонов."
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="➕ Создать шаблон", callback_data="templates_create")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_templates")
                    ]
                ]
            )
        else:
            text = f"📝 <b>Ваши шаблоны ({len(templates_list)})</b>\n\n"

            keyboard_buttons = []

            for template in templates_list:
                status_emoji = "✅" if template['is_active'] else "❌"
                text += f"{status_emoji} <b>{template['name']}</b>\n"
                text += f"   • Категория: {template['category'] or 'Общая'}\n"
                text += f"   • Использований: {template['usage_count']}\n"
                text += f"   • Конверсия: {template['conversion_rate']:.1f}%\n\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📝 {template['name'][:20]}...",
                        callback_data=f"template_view_{template['id']}"
                    )
                ])

            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="➕ Создать шаблон", callback_data="templates_create"),
                    InlineKeyboardButton(text="📊 Статистика", callback_data="templates_stats")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="templates_view_all"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_templates")
                ]
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки шаблонов: {e}")
        await callback.answer("❌ Ошибка загрузки шаблонов")


@template_handlers_router.callback_query(F.data.startswith("template_view_"))
async def template_view_specific(callback: CallbackQuery):
    """Просмотр конкретного шаблона"""

    try:
        template_id = int(callback.data.split("_")[-1])

        template = await template_manager.get_template(template_id)
        if not template:
            await callback.answer("❌ Шаблон не найден")
            return

        stats = await template_manager.get_template_stats(template_id)

        # Предпросмотр
        preview = await template_manager.preview_substitution(
            template.text,
            {"username": "example_user", "first_name": "Иван"}
        )

        text = f"""📝 <b>{template.name}</b>

📝 <b>Описание:</b> {template.description or 'Без описания'}
🏷️ <b>Категория:</b> {template.category or 'Общая'}

💬 <b>Текст шаблона:</b>
<pre>{template.text}</pre>

📱 <b>Предпросмотр:</b>
<pre>{preview}</pre>

📊 <b>Статистика:</b>
• Использований: {stats['usage_count']}
• Отправлено: {stats['total_sent']}
• Доставлено: {stats['successful_sent']} ({stats['delivery_rate']:.1f}%)
• Ответов: {stats['response_count']} ({stats['response_rate']:.1f}%)

📅 <b>Создан:</b> {stats['created_at'].strftime('%d.%m.%Y %H:%M')}"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚀 Создать кампанию",
                        callback_data=f"campaigns_create_with_template_{template_id}"
                    ),
                    InlineKeyboardButton(
                        text="📊 Предложения",
                        callback_data=f"template_suggestions_{template_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📋 Дублировать",
                        callback_data=f"template_duplicate_{template_id}"
                    ),
                    InlineKeyboardButton(
                        text="🗑️ Удалить",
                        callback_data=f"template_delete_{template_id}"
                    )
                ],
                [
                    InlineKeyboardButton(text="📚 Все шаблоны", callback_data="templates_view_all"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_templates")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка просмотра шаблона: {e}")
        await callback.answer("❌ Ошибка загрузки шаблона")


@template_handlers_router.callback_query(F.data.startswith("template_suggestions_"))
async def template_suggestions(callback: CallbackQuery):
    """Предложения по улучшению шаблона"""

    try:
        template_id = int(callback.data.split("_")[-1])

        suggestions = await template_manager.suggest_improvements(template_id)

        if not suggestions:
            text = "💡 <b>Предложения по улучшению</b>\n\n✅ Шаблон выглядит хорошо! Никаких предложений."
        else:
            text = "💡 <b>Предложения по улучшению шаблона:</b>\n\n"
            for i, suggestion in enumerate(suggestions, 1):
                text += f"{i}. {suggestion}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔙 К шаблону",
                    callback_data=f"template_view_{template_id}"
                )
            ]]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка получения предложений: {e}")
        await callback.answer("❌ Ошибка получения предложений")


# Обработчик отмены
@template_handlers_router.message(lambda message: message.text == "/cancel")
async def cancel_template_action(message: Message, state: FSMContext):
    """Отмена действия с шаблонами"""

    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К шаблонам", callback_data="outreach_templates")
            ]]
        )
    )


# cold_outreach/bot_handlers/template_handlers.py - НЕДОСТАЮЩИЕ ОБРАБОТЧИКИ

@template_handlers_router.callback_query(F.data.startswith("template_duplicate_"))
async def template_duplicate_handler(callback: CallbackQuery):
    """Дублирование шаблона"""
    try:
        template_id = int(callback.data.split("_")[-1])

        # Получаем оригинальный шаблон
        template = await template_manager.get_template(template_id)
        if not template:
            await callback.answer("❌ Шаблон не найден")
            return

        # Создаем копию
        new_name = f"Копия - {template.name}"
        new_template_id = await template_manager.duplicate_template(template_id, new_name)

        if new_template_id:
            text = f"✅ <b>Шаблон продублирован</b>\n\nНовый шаблон: '{new_name}'"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📝 Редактировать копию",
                            callback_data=f"template_view_{new_template_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(text="📚 Все шаблоны", callback_data="templates_view_all")
                    ]
                ]
            )
        else:
            text = "❌ Ошибка дублирования шаблона"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data=f"template_view_{template_id}")
                ]]
            )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка дублирования шаблона: {e}")
        await callback.answer("❌ Ошибка дублирования")


@template_handlers_router.callback_query(F.data.startswith("template_delete_"))
async def template_delete_handler(callback: CallbackQuery):
    """Удаление шаблона"""
    try:
        template_id = int(callback.data.split("_")[-1])

        template = await template_manager.get_template(template_id)
        if not template:
            await callback.answer("❌ Шаблон не найден")
            return

        text = f"""🗑️ <b>Удаление шаблона</b>

📝 <b>Шаблон:</b> {template.name}

⚠️ <b>Внимание!</b> Шаблон будет деактивирован (не удален полностью).

Продолжить?"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑️ Да, удалить",
                        callback_data=f"template_delete_confirm_{template_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"template_view_{template_id}"
                    )
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка удаления шаблона: {e}")
        await callback.answer("❌ Ошибка")


@template_handlers_router.callback_query(F.data.startswith("template_delete_confirm_"))
async def template_delete_confirm_handler(callback: CallbackQuery):
    """Подтверждение удаления шаблона"""
    try:
        template_id = int(callback.data.split("_")[-1])

        success = await template_manager.delete_template(template_id)

        if success:
            text = "✅ <b>Шаблон удален</b>\n\nШаблон деактивирован и больше не будет использоваться."
        else:
            text = "❌ <b>Ошибка удаления</b>\n\nНе удалось удалить шаблон."

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="📚 Все шаблоны", callback_data="templates_view_all")
            ]]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка подтверждения удаления: {e}")
        await callback.answer("❌ Ошибка удаления")


@template_handlers_router.callback_query(F.data == "templates_by_persona")
async def templates_by_persona_handler(callback: CallbackQuery):
    """Шаблоны по персонам"""
    text = """🎭 <b>Шаблоны по персонам</b>

Выберите тип персоны для просмотра шаблонов:"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨‍💼 Базовый мужчина", callback_data="templates_persona_basic_man"),
                InlineKeyboardButton(text="👩‍💼 Базовая женщина", callback_data="templates_persona_basic_woman")
            ],
            [
                InlineKeyboardButton(text="💰 HYIP мужчина", callback_data="templates_persona_hyip_man"),
                InlineKeyboardButton(text="💎 HYIP женщина", callback_data="templates_persona_hyip_woman")
            ],
            [
                InlineKeyboardButton(text="📈 Инвестор", callback_data="templates_persona_investor"),
                InlineKeyboardButton(text="📝 Все шаблоны", callback_data="templates_view_all")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_templates")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@template_handlers_router.callback_query(F.data == "templates_stats")
async def templates_stats_handler(callback: CallbackQuery):
    """Общая статистика шаблонов"""
    try:
        # Получаем общую статистику
        templates_list = await template_manager.get_templates_list(limit=100)

        total_templates = len(templates_list)
        active_templates = sum(1 for t in templates_list if t.get('is_active', False))

        # Статистика использования
        total_usage = sum(t.get('usage_count', 0) for t in templates_list)
        avg_conversion = sum(t.get('conversion_rate', 0) for t in templates_list) / max(total_templates, 1)

        # Топ переменных
        variables_usage = await template_manager.get_template_variables_usage()
        top_variables = list(variables_usage.items())[:5]

        text = f"""📊 <b>Статистика шаблонов</b>

📝 <b>Общее:</b>
• Всего шаблонов: {total_templates}
• Активных: {active_templates}
• Общее использование: {total_usage}
• Средняя конверсия: {avg_conversion:.1f}%

🔤 <b>Топ переменных:</b>"""

        for var, count in top_variables:
            text += f"\n• {{{var}}}: {count} раз"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📈 Детальная аналитика", callback_data="analytics_templates")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_templates")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики шаблонов: {e}")
        await callback.answer("❌ Ошибка загрузки статистики")


@template_handlers_router.callback_query(F.data.startswith("template_suggestions_"))
async def template_suggestions(callback: CallbackQuery):
    """Предложения по улучшению шаблона"""
    try:
        template_id = int(callback.data.split("_")[-1])
        suggestions = await template_manager.suggest_improvements(template_id)

        if not suggestions:
            text = "💡 <b>Предложения по улучшению</b>\n\n✅ Шаблон выглядит хорошо! Никаких предложений."
        else:
            text = "💡 <b>Предложения по улучшению шаблона:</b>\n\n"
            for i, suggestion in enumerate(suggestions, 1):
                text += f"{i}. {suggestion}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К шаблону", callback_data=f"template_view_{template_id}")
            ]]
        )
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"❌ Ошибка получения предложений: {e}")
        await callback.answer("❌ Ошибка получения предложений")


@template_handlers_router.callback_query(F.data.startswith("templates_persona_"))
async def templates_by_persona_specific(callback: CallbackQuery):
    """Шаблоны по конкретной персоне"""
    try:
        persona_type = callback.data.replace("templates_persona_", "")
        templates = await template_manager.get_templates_by_persona(persona_type)

        persona_names = {
            "basic_man": "👨‍💼 Базовый мужчина",
            "basic_woman": "👩‍💼 Базовая женщина",
            "hyip_man": "💰 HYIP мужчина",
            "hyip_woman": "💎 HYIP женщина",
            "investor": "📈 Инвестор"
        }

        persona_name = persona_names.get(persona_type, persona_type)

        if not templates:
            text = f"🎭 <b>Шаблоны: {persona_name}</b>\n\n📭 Шаблонов для этой персоны пока нет."
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Создать", callback_data="templates_create")],
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="templates_by_persona")]
                ]
            )
        else:
            text = f"🎭 <b>Шаблоны: {persona_name}</b>\n\n📊 <b>Найдено:</b> {len(templates)}\n\n"

            keyboard_buttons = []
            for template in templates[:8]:
                text += f"📝 <b>{template.name}</b>\n   📊 {template.usage_count} использований\n\n"
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📝 {template.name[:25]}...",
                        callback_data=f"template_view_{template.id}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton(text="🔙 К персонам", callback_data="templates_by_persona")
            ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки шаблонов персоны: {e}")
        await callback.answer("❌ Ошибка загрузки")


@template_handlers_router.callback_query(F.data.startswith("campaigns_create_with_template_"))
async def create_campaign_with_template(callback: CallbackQuery):
    """Создание кампании с выбранным шаблоном"""
    try:
        template_id = int(callback.data.split("_")[-1])

        # Пока заглушка - перенаправляем в кампании
        text = f"""🚀 <b>Создание кампании</b>

📝 <b>Выбран шаблон ID:</b> {template_id}

⚠️ <b>Функция в разработке</b>

Скоро здесь будет мастер создания кампании с автоматическим выбором этого шаблона."""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚀 Кампании", callback_data="outreach_campaigns")
                ],
                [
                    InlineKeyboardButton(text="🔙 К шаблону", callback_data=f"template_view_{template_id}")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка создания кампании: {e}")
        await callback.answer("❌ Ошибка")


# Обработчик отмены для всех состояний
@template_handlers_router.message(F.text == "/cancel")
async def cancel_template_action(message: Message, state: FSMContext):
    """Отмена действия с шаблонами"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К шаблонам", callback_data="outreach_templates")
            ]]
        )
    )