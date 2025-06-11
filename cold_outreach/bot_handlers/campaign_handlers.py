# cold_outreach/bot_handlers/campaign_handlers.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from cold_outreach.campaigns.campaign_manager import campaign_manager
from cold_outreach.leads.lead_manager import lead_manager
from cold_outreach.templates.template_manager import template_manager
from cold_outreach.core import outreach_manager
from loguru import logger

campaign_handlers_router = Router()


class CampaignStates(StatesGroup):
    """Состояния для создания кампаний"""
    waiting_name = State()
    waiting_description = State()
    selecting_list = State()
    selecting_template = State()
    selecting_sessions = State()
    configuring_settings = State()


@campaign_handlers_router.callback_query(F.data == "campaigns_create")
async def campaigns_create_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания кампании"""

    text = """🚀 <b>Создание новой кампании рассылки</b>

📝 Введите название кампании:

Например: "Привлечение в проект X", "Январская рассылка", "Тест нового шаблона"

💡 Название поможет отличать кампании в списке."""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_campaigns")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(CampaignStates.waiting_name)


@campaign_handlers_router.message(CampaignStates.waiting_name)
async def campaigns_create_name(message: Message, state: FSMContext):
    """Получение названия кампании"""

    campaign_name = message.text.strip()

    if not campaign_name or len(campaign_name) < 3:
        await message.answer("❌ Название должно содержать минимум 3 символа. Попробуйте еще раз:")
        return

    await state.update_data(campaign_name=campaign_name)

    text = f"""🚀 <b>Кампания: "{campaign_name}"</b>

📝 Введите описание кампании (необязательно):

Опишите цель кампании, целевую аудиторию, особенности.

Или отправьте "-" чтобы пропустить описание."""

    await message.answer(text)
    await state.set_state(CampaignStates.waiting_description)


@campaign_handlers_router.message(CampaignStates.waiting_description)
async def campaigns_create_description(message: Message, state: FSMContext):
    """Получение описания кампании"""

    description = message.text.strip() if message.text.strip() != "-" else None
    await state.update_data(description=description)

    # Получаем доступные списки лидов
    try:
        lists_data = await lead_manager.get_all_lists()

        if not lists_data:
            text = """❌ <b>Нет списков лидов</b>

Для создания кампании нужен хотя бы один список лидов.

Сначала создайте список лидов."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📝 Создать список", callback_data="leads_create_list")
                    ],
                    [
                        InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_campaigns")
                    ]
                ]
            )

            await message.answer(text, reply_markup=keyboard)
            await state.clear()
            return

        data = await state.get_data()
        campaign_name = data["campaign_name"]

        text = f"""🚀 <b>Кампания: "{campaign_name}"</b>

📋 Выберите список лидов для рассылки:

Найдено списков: {len(lists_data)}"""

        keyboard_buttons = []
        for lst in lists_data[:10]:  # Показываем первые 10
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📋 {lst['name']} ({lst['total_leads']} лидов)",
                    callback_data=f"campaign_select_list_{lst['id']}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_campaigns")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await message.answer(text, reply_markup=keyboard)
        await state.set_state(CampaignStates.selecting_list)

    except Exception as e:
        logger.error(f"❌ Ошибка получения списков лидов: {e}")
        await message.answer("❌ Ошибка загрузки списков лидов")
        await state.clear()


@campaign_handlers_router.callback_query(F.data.startswith("campaign_select_list_"), CampaignStates.selecting_list)
async def campaigns_select_list(callback: CallbackQuery, state: FSMContext):
    """Выбор списка лидов"""

    try:
        list_id = int(callback.data.split("_")[-1])
        await state.update_data(lead_list_id=list_id)

        # Получаем доступные шаблоны
        templates_list = await template_manager.get_templates_list(limit=20)

        if not templates_list:
            text = """❌ <b>Нет шаблонов сообщений</b>

Для создания кампании нужен хотя бы один шаблон сообщения.

Сначала создайте шаблон."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📝 Создать шаблон", callback_data="templates_create")
                    ],
                    [
                        InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_campaigns")
                    ]
                ]
            )

            await callback.message.edit_text(text, reply_markup=keyboard)
            await state.clear()
            return

        data = await state.get_data()
        campaign_name = data["campaign_name"]

        text = f"""🚀 <b>Кампания: "{campaign_name}"</b>

📝 Выберите шаблон сообщения:

Найдено шаблонов: {len(templates_list)}"""

        keyboard_buttons = []
        for template in templates_list[:10]:  # Показываем первые 10
            template_type = "📺" if template.get("category") == "channel_post" else "📝"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{template_type} {template['name'][:30]}...",
                    callback_data=f"campaign_select_template_{template['id']}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_campaigns")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(CampaignStates.selecting_template)

    except Exception as e:
        logger.error(f"❌ Ошибка выбора списка лидов: {e}")
        await callback.answer("❌ Ошибка выбора списка")


@campaign_handlers_router.callback_query(F.data.startswith("campaign_select_template_"),
                                         CampaignStates.selecting_template)
async def campaigns_select_template(callback: CallbackQuery, state: FSMContext):
    """Выбор шаблона сообщения"""

    try:
        template_id = int(callback.data.split("_")[-1])
        await state.update_data(template_id=template_id)

        data = await state.get_data()
        campaign_name = data["campaign_name"]

        # Пока создаем кампанию с базовыми настройками
        # В будущем можно добавить выбор сессий и настройки

        text = f"""🚀 <b>Создание кампании: "{campaign_name}"</b>

⏳ Создаем кампанию с базовыми настройками...

📊 <b>Параметры:</b>
• Лимит: 5 сообщений в день
• Задержка: 30 минут между сообщениями
• Время работы: 10:00-18:00
• Все доступные сессии"""

        await callback.message.edit_text(text)

        # Создаем кампанию
        campaign_id = await campaign_manager.create_campaign(
            name=campaign_name,
            description=data.get("description", ""),
            lead_list_id=data["lead_list_id"],
            template_id=template_id,
            session_names=[],  # Пустой список - будет заполнен автоматически
            settings={
                "max_messages_per_day": 5,
                "delay_between_messages": 1800,
                "session_daily_limit": 5,
                "daily_start_hour": 10,
                "daily_end_hour": 18
            }
        )

        if campaign_id:
            text = f"""✅ <b>Кампания создана!</b>

🚀 <b>Название:</b> {campaign_name}
🆔 <b>ID:</b> {campaign_id}
📊 <b>Статус:</b> Черновик

🎯 <b>Что дальше?</b>
Кампания создана в статусе "черновик". Вы можете настроить её или сразу запустить.

⚠️ <b>Внимание:</b> Перед запуском убедитесь что у вас есть активные сессии."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🚀 Запустить кампанию",
                            callback_data=f"campaign_start_{campaign_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⚙️ Настроить",
                            callback_data=f"campaign_settings_{campaign_id}"
                        ),
                        InlineKeyboardButton(
                            text="📊 Просмотр",
                            callback_data=f"campaign_view_{campaign_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(text="📋 Все кампании", callback_data="campaigns_view_all"),
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_campaigns")
                    ]
                ]
            )
        else:
            text = """❌ <b>Ошибка создания кампании</b>

Не удалось создать кампанию. Проверьте логи для получения подробностей."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_campaigns")
                ]]
            )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка создания кампании: {e}")
        await callback.message.edit_text(f"❌ Ошибка создания кампании: {str(e)}")

    await state.clear()


@campaign_handlers_router.callback_query(F.data == "campaigns_view_all")
async def campaigns_view_all(callback: CallbackQuery):
    """Просмотр всех кампаний"""

    try:
        from storage.database import get_db
        from storage.models.cold_outreach import OutreachCampaign
        from sqlalchemy import select, desc

        async with get_db() as db:
            result = await db.execute(
                select(OutreachCampaign)
                .order_by(desc(OutreachCampaign.created_at))
                .limit(10)
            )
            campaigns = result.scalars().all()

        if not campaigns:
            text = """📋 <b>Кампании рассылки</b>

📭 У вас пока нет кампаний.

Создайте первую кампанию для начала работы с системой рассылки."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🚀 Создать кампанию", callback_data="campaigns_create")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_campaigns")
                    ]
                ]
            )
        else:
            text = f"""📋 <b>Все кампании ({len(campaigns)})</b>

"""

            keyboard_buttons = []

            for campaign in campaigns:
                status_emoji = {
                    "draft": "📝",
                    "active": "🚀",
                    "paused": "⏸️",
                    "completed": "✅",
                    "failed": "❌"
                }.get(campaign.status, "❓")

                progress = 0
                if campaign.total_targets > 0:
                    progress = (campaign.processed_targets / campaign.total_targets) * 100

                text += f"{status_emoji} <b>{campaign.name}</b>\n"
                text += f"   📊 Прогресс: {campaign.processed_targets}/{campaign.total_targets} ({progress:.1f}%)\n"
                text += f"   📅 Создана: {campaign.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"{status_emoji} {campaign.name[:20]}...",
                        callback_data=f"campaign_stats_{campaign.id}"
                    ),
                    InlineKeyboardButton(
                        text="🚀" if campaign.status == "draft" else "⏸️",
                        callback_data=f"campaign_start_{campaign.id}" if campaign.status == "draft" else f"campaign_stop_{campaign.id}"
                    )
                ])

            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="🚀 Создать новую", callback_data="campaigns_create")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="campaigns_view_all"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_campaigns")
                ]
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка просмотра кампаний: {e}")
        await callback.answer("❌ Ошибка загрузки кампаний")


@campaign_handlers_router.callback_query(F.data == "campaigns_active")
async def campaigns_active(callback: CallbackQuery):
    """Просмотр активных кампаний"""

    try:
        from cold_outreach.core.outreach_manager import outreach_manager

        active_campaigns = await outreach_manager.get_active_campaigns()

        if not active_campaigns:
            text = """▶️ <b>Активные кампании</b>

📭 Нет активных кампаний рассылки.

Создайте и запустите кампанию для начала работы."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🚀 Создать кампанию", callback_data="campaigns_create")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_campaigns")
                    ]
                ]
            )
        else:
            text = f"""▶️ <b>Активные кампании ({len(active_campaigns)})</b>

"""

            keyboard_buttons = []

            for campaign in active_campaigns:
                text += f"🚀 <b>{campaign['name']}</b>\n"
                text += f"   📊 Прогресс: {campaign['processed_targets']}/{campaign['total_targets']} ({campaign['progress_percent']}%)\n"
                text += f"   ✅ Успешно: {campaign['successful_sends']}\n"
                text += f"   ❌ Неудачно: {campaign['failed_sends']}\n\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"🚀 {campaign['name'][:25]}...",
                        callback_data=f"campaign_view_{campaign['campaign_id']}"
                    )
                ])

            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="campaigns_active"),
                    InlineKeyboardButton(text="📊 Мониторинг", callback_data="campaigns_monitor")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_campaigns")
                ]
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка просмотра активных кампаний: {e}")
        await callback.answer("❌ Ошибка загрузки")


@campaign_handlers_router.callback_query(F.data == "campaigns_monitor")
async def campaigns_monitor(callback: CallbackQuery):
    """Мониторинг кампаний в реальном времени"""

    text = """📈 <b>Мониторинг кампаний</b>

⚠️ <b>Функция в разработке</b>

Здесь будет отображаться:
• Статистика в реальном времени
• График прогресса
• Статус сессий
• Ошибки и блокировки
• Прогнозы завершения"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Активные", callback_data="campaigns_active")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_campaigns")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


# Заглушки для будущих обработчиков
@campaign_handlers_router.callback_query(F.data.startswith("campaign_start_"))
async def campaign_start_handler(callback: CallbackQuery):
    """Запуск кампании"""
    try:
        campaign_id = int(callback.data.split("_")[-1])

        # Показываем индикатор
        await callback.message.edit_text("🚀 Запускаем кампанию...")

        # Запускаем через outreach_manager
        success = await outreach_manager.start_campaign(campaign_id)

        if success:
            text = f"✅ <b>Кампания {campaign_id} запущена!</b>\n\nСессии переключены в режим рассылки."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Мониторинг", callback_data="campaigns_monitor")],
                [InlineKeyboardButton(text="🔙 К кампаниям", callback_data="outreach_campaigns")]
            ])
        else:
            text = "❌ Не удалось запустить кампанию. Проверьте логи."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К кампаниям", callback_data="outreach_campaigns")]
            ])

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка запуска: {str(e)}")


@campaign_handlers_router.callback_query(F.data.startswith("campaign_stop_"))
async def campaign_stop_handler(callback: CallbackQuery):
    """Остановка кампании"""
    try:
        campaign_id = int(callback.data.split("_")[-1])

        await callback.message.edit_text("⏸️ Останавливаем кампанию...")

        success = await outreach_manager.stop_campaign(campaign_id)

        if success:
            text = f"⏸️ <b>Кампания {campaign_id} остановлена</b>\n\nСессии переведены в режим ответов."
        else:
            text = "❌ Не удалось остановить кампанию"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data=f"campaign_stats_{campaign_id}")],
            [InlineKeyboardButton(text="🔙 К кампаниям", callback_data="outreach_campaigns")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка остановки: {str(e)}")


@campaign_handlers_router.callback_query(F.data.startswith("campaign_stats_"))
async def campaign_stats_handler(callback: CallbackQuery):
    """Статистика кампании"""
    try:
        campaign_id = int(callback.data.split("_")[-1])

        progress = await campaign_manager.get_campaign_progress(campaign_id)

        if not progress:
            await callback.answer("❌ Кампания не найдена")
            return

        text = f"""📊 <b>Статистика: {progress['name']}</b>

📈 <b>Прогресс:</b>
- Обработано: {progress['processed_targets']}/{progress['total_targets']} ({progress['progress_percent']}%)
- Успешно: {progress['successful_sends']}
- Неудачно: {progress['failed_sends']}

📅 <b>Время:</b>
- Запущена: {progress['started_at'].strftime('%d.%m.%Y %H:%M') if progress['started_at'] else 'Не запускалась'}
- Последняя активность: {progress['last_activity'].strftime('%d.%m.%Y %H:%M') if progress['last_activity'] else 'Нет'}

📊 <b>Статус:</b> {progress['status']}"""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"campaign_stats_{campaign_id}")],
            [InlineKeyboardButton(text="🔙 К кампаниям", callback_data="outreach_campaigns")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка загрузки статистики: {str(e)}")

@campaign_handlers_router.callback_query(F.data.startswith("campaign_view_"))
async def campaign_view_handler(callback: CallbackQuery):
    """Просмотр кампании"""

    campaign_id = int(callback.data.split("_")[-1])

    text = f"""📊 <b>Просмотр кампании</b>

⚠️ <b>Функция в разработке</b>

Кампания ID: {campaign_id}

Скоро здесь будет детальная информация о кампании."""

    await callback.answer("⚠️ Функция в разработке")


@campaign_handlers_router.callback_query(F.data.startswith("campaign_settings_"))
async def campaign_settings_handler(callback: CallbackQuery):
    """Настройки кампании"""

    campaign_id = int(callback.data.split("_")[-1])

    text = f"""⚙️ <b>Настройки кампании</b>

⚠️ <b>Функция в разработке</b>

Кампания ID: {campaign_id}

Скоро здесь будут настройки лимитов, времени работы, сессий."""

    await callback.answer("⚠️ Функция в разработке")


# Обработчик отмены
@campaign_handlers_router.message(F.text == "/cancel")
async def cancel_campaign_action(message: Message, state: FSMContext):
    """Отмена действия с кампаниями"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К кампаниям", callback_data="outreach_campaigns")
            ]]
        )
    )