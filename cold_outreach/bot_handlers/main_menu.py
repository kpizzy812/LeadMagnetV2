# cold_outreach/bot_handlers/main_menu.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from cold_outreach.core.outreach_manager import outreach_manager
from cold_outreach.bot_handlers.lead_handlers import leads_handlers_router
from cold_outreach.bot_handlers.template_handlers import template_handlers_router
from cold_outreach.bot_handlers.channel_post_handlers import channel_post_router  # НОВОЕ
from cold_outreach.bot_handlers.analytics_handlers import analytics_handlers_router  # НОВОЕ
from loguru import logger

outreach_router = Router()

# Включаем дочерние роутеры
outreach_router.include_router(leads_handlers_router)
outreach_router.include_router(template_handlers_router)
outreach_router.include_router(channel_post_router)  # НОВОЕ
outreach_router.include_router(analytics_handlers_router)  # НОВОЕ

@outreach_router.callback_query(F.data == "outreach_main")
async def outreach_main_menu(callback: CallbackQuery):
    """Главное меню холодной рассылки"""

    try:
        # Получаем статистику
        active_campaigns = await outreach_manager.get_active_campaigns()
        session_stats = await outreach_manager.get_session_outreach_stats()

        available_sessions = sum(1 for stats in session_stats.values() if stats.get("can_send", False))
        blocked_sessions = sum(1 for stats in session_stats.values() if stats.get("is_blocked", False))

        text = f"""📤 <b>Система холодной рассылки</b>

📊 <b>Текущий статус:</b>
• Активных кампаний: {len(active_campaigns)}
• Доступных сессий: {available_sessions}
• Заблокированных сессий: {blocked_sessions}

🎯 <b>Возможности:</b>
• 📋 Управление списками лидов
• 📝 Создание шаблонов сообщений
• 📺 Пересылка постов из каналов
• 🚀 Запуск кампаний рассылки
• 📈 Аналитика и отчеты

⚠️ <b>Внимание:</b> Система автоматически управляет лимитами и безопасностью отправки."""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📋 Списки лидов", callback_data="outreach_leads"),
                    InlineKeyboardButton(text="📝 Шаблоны", callback_data="outreach_templates")
                ],
                [
                    InlineKeyboardButton(text="🚀 Кампании", callback_data="outreach_campaigns"),
                    InlineKeyboardButton(text="📈 Аналитика", callback_data="outreach_analytics")
                ],
                [
                    InlineKeyboardButton(text="⚙️ Сессии", callback_data="outreach_sessions"),
                    InlineKeyboardButton(text="🔒 Безопасность", callback_data="outreach_safety")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка главного меню рассылки: {e}")
        await callback.answer("❌ Ошибка загрузки меню")


@outreach_router.callback_query(F.data == "outreach_leads")
async def outreach_leads_menu(callback: CallbackQuery):
    """Меню управления лидами"""

    try:
        from cold_outreach.leads.lead_manager import LeadManager
        lead_manager = LeadManager()

        # Получаем статистику списков
        lists_data = await lead_manager.get_all_lists()

        total_lists = len(lists_data)
        total_leads = sum(lst.get("total_leads", 0) for lst in lists_data)

        text = f"""📋 <b>Управление списками лидов</b>

📊 <b>Статистика:</b>
• Всего списков: {total_lists}
• Общее количество лидов: {total_leads}

🔧 <b>Возможности:</b>
• Создание новых списков
• Импорт лидов из текста/CSV
• Управление дубликатами
• Анализ и очистка данных"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📝 Создать список", callback_data="leads_create_list"),
                    InlineKeyboardButton(text="📥 Импорт лидов", callback_data="leads_import")
                ],
                [
                    InlineKeyboardButton(text="📚 Все списки", callback_data="leads_view_all"),
                    InlineKeyboardButton(text="🔍 Поиск дубликатов", callback_data="leads_duplicates")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню лидов: {e}")
        await callback.answer("❌ Ошибка загрузки")


@outreach_router.callback_query(F.data == "outreach_templates")
async def outreach_templates_menu(callback: CallbackQuery):
    """Меню управления шаблонами с поддержкой постов каналов"""

    try:
        from cold_outreach.templates.template_manager import TemplateManager
        template_manager = TemplateManager()

        # Получаем статистику шаблонов
        templates_list = await template_manager.get_templates_list(limit=100)
        channel_templates = await template_manager.get_channel_templates()

        total_templates = len(templates_list)
        active_templates = sum(1 for t in templates_list if t.get("is_active", False))
        channel_posts_count = len(channel_templates)

        text = f"""📝 <b>Управление шаблонами сообщений</b>

📊 <b>Статистика:</b>
• Всего шаблонов: {total_templates}
• Активных: {active_templates}
• Постов из каналов: {channel_posts_count}

🎯 <b>Типы шаблонов:</b>
• 📝 Текстовые сообщения с переменными
• 📺 Посты из ваших каналов
• 🎭 Персонализированные по персонам
• 🤖 ИИ уникализация текста

💡 <b>Возможности:</b>
• Создание и редактирование
• Тестирование перед использованием
• Анализ эффективности
• Массовое управление"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Текстовый шаблон", callback_data="templates_create"),
                    InlineKeyboardButton(text="📺 Из канала", callback_data="templates_create_from_channel")
                ],
                [
                    InlineKeyboardButton(text="📚 Все шаблоны", callback_data="templates_view_all"),
                    InlineKeyboardButton(text="📺 Посты каналов", callback_data="templates_view_channel_posts")
                ],
                [
                    InlineKeyboardButton(text="🎭 По персонам", callback_data="templates_by_persona"),
                    InlineKeyboardButton(text="📈 Статистика", callback_data="templates_stats")
                ],
                [
                    InlineKeyboardButton(text="❓ Справка", callback_data="templates_channel_help"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню шаблонов: {e}")
        await callback.answer("❌ Ошибка загрузки")


@outreach_router.callback_query(F.data == "outreach_campaigns")
async def outreach_campaigns_menu(callback: CallbackQuery):
    """Меню управления кампаниями"""

    try:
        from cold_outreach.campaigns.campaign_manager import CampaignManager
        from storage.database import get_db
        from storage.models.cold_outreach import OutreachCampaign
        from sqlalchemy import select, func

        # Получаем статистику кампаний
        async with get_db() as db:
            total_result = await db.execute(select(func.count(OutreachCampaign.id)))
            total_campaigns = total_result.scalar() or 0

            active_result = await db.execute(
                select(func.count(OutreachCampaign.id))
                .where(OutreachCampaign.status == "active")
            )
            active_campaigns = active_result.scalar() or 0

            completed_result = await db.execute(
                select(func.count(OutreachCampaign.id))
                .where(OutreachCampaign.status == "completed")
            )
            completed_campaigns = completed_result.scalar() or 0

        text = f"""🚀 <b>Управление кампаниями рассылки</b>

📊 <b>Статистика:</b>
• Всего кампаний: {total_campaigns}
• Активных: {active_campaigns}
• Завершенных: {completed_campaigns}

⚡ <b>Возможности:</b>
• Создание новых кампаний
• Мониторинг в реальном времени
• Управление запуском/остановкой
• Детальная аналитика

🎯 <b>Настройки:</b>
• Автоматические лимиты
• Умное распределение нагрузки
• Восстановление после блокировок
• Временные ограничения"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Новая кампания", callback_data="campaigns_create"),
                    InlineKeyboardButton(text="📋 Все кампании", callback_data="campaigns_view_all")
                ],
                [
                    InlineKeyboardButton(text="▶️ Активные", callback_data="campaigns_active"),
                    InlineKeyboardButton(text="📈 Мониторинг", callback_data="campaigns_monitor")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню кампаний: {e}")
        await callback.answer("❌ Ошибка загрузки")


@outreach_router.callback_query(F.data == "outreach_sessions")
async def outreach_sessions_menu(callback: CallbackQuery):
    """Меню управления сессиями для рассылки"""

    try:
        # Получаем статистику сессий
        session_stats = await outreach_manager.get_session_outreach_stats()

        total_sessions = len(session_stats)
        outreach_mode = sum(1 for stats in session_stats.values() if stats.get("mode") == "outreach")
        response_mode = sum(1 for stats in session_stats.values() if stats.get("mode") == "response")
        blocked_sessions = sum(1 for stats in session_stats.values() if stats.get("is_blocked", False))

        text = f"""⚙️ <b>Управление сессиями рассылки</b>

📊 <b>Статистика сессий:</b>
• Всего сессий: {total_sessions}
• В режиме рассылки: {outreach_mode}
• В режиме ответов: {response_mode}
• Заблокированных: {blocked_sessions}

🔄 <b>Режимы работы:</b>
• <code>outreach</code> - отправка холодных сообщений
• <code>response</code> - обработка входящих

⚠️ <b>Важно:</b> Сессии автоматически переключаются между режимами в зависимости от активности кампаний."""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Статистика сессий", callback_data="sessions_outreach_stats"),
                    InlineKeyboardButton(text="🔧 Настройки лимитов", callback_data="sessions_limits")
                ],
                [
                    InlineKeyboardButton(text="🚫 Заблокированные", callback_data="sessions_blocked"),
                    InlineKeyboardButton(text="🔄 Переключить режимы", callback_data="sessions_switch_modes")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню сессий: {e}")
        await callback.answer("❌ Ошибка загрузки")


@outreach_router.callback_query(F.data == "outreach_safety")
async def outreach_safety_menu(callback: CallbackQuery):
    """Меню безопасности рассылки"""

    try:
        from cold_outreach.safety.error_handler import OutreachErrorHandler
        from cold_outreach.safety.rate_limiter import RateLimiter

        error_handler = OutreachErrorHandler()
        rate_limiter = RateLimiter()

        # Получаем статистику безопасности
        blocked_stats = await error_handler.get_blocked_sessions_stats()
        rate_stats = await rate_limiter.get_sessions_stats()

        text = f"""🔒 <b>Система безопасности рассылки</b>

🚫 <b>Блокировки:</b>
• FloodWait сессий: {blocked_stats.get('flood_wait_sessions', 0)}
• Заблокированных сессий: {blocked_stats.get('blocked_sessions', 0)}
• Общее количество: {blocked_stats.get('total_blocked', 0)}

⚡ <b>Лимиты:</b>
• Активных лимитов: {len(rate_stats)}
• Автоматическое управление скоростью
• Умные задержки между сообщениями

🛡️ <b>Защита:</b>
• Автоматическое восстановление через @spambot
• Ротация сессий при блокировках
• Мониторинг подозрительной активности
• Соблюдение лимитов Telegram"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚫 Заблокированные", callback_data="safety_blocked_sessions"),
                    InlineKeyboardButton(text="⚡ Лимиты", callback_data="safety_rate_limits")
                ],
                [
                    InlineKeyboardButton(text="🔧 Восстановление", callback_data="safety_recovery"),
                    InlineKeyboardButton(text="📊 Статистика", callback_data="safety_stats")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню безопасности: {e}")
        await callback.answer("❌ Ошибка загрузки")


@outreach_router.callback_query(F.data == "outreach_analytics")
async def outreach_analytics_menu(callback: CallbackQuery):
    """Меню аналитики рассылки"""

    try:
        from storage.database import get_db
        from storage.models.cold_outreach import OutreachMessage, OutreachMessageStatus
        from sqlalchemy import select, func
        from datetime import datetime, timedelta

        # Получаем статистику за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(hours=24)

        async with get_db() as db:
            # Всего отправлено за 24ч
            sent_24h_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.sent_at >= yesterday,
                    OutreachMessage.status == OutreachMessageStatus.SENT
                )
            )
            sent_24h = sent_24h_result.scalar() or 0

            # Получено ответов за 24ч
            responses_24h_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.sent_at >= yesterday,
                    OutreachMessage.got_response == True
                )
            )
            responses_24h = responses_24h_result.scalar() or 0

            # Конверсии за 24ч
            conversions_24h_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.sent_at >= yesterday,
                    OutreachMessage.converted == True
                )
            )
            conversions_24h = conversions_24h_result.scalar() or 0

        # Рассчитываем показатели
        response_rate = (responses_24h / max(sent_24h, 1)) * 100
        conversion_rate = (conversions_24h / max(sent_24h, 1)) * 100

        text = f"""📈 <b>Аналитика холодной рассылки</b>

📊 <b>За последние 24 часа:</b>
• Отправлено сообщений: {sent_24h}
• Получено ответов: {responses_24h}
• Конверсий: {conversions_24h}

📈 <b>Показатели:</b>
• Response Rate: {response_rate:.1f}%
• Conversion Rate: {conversion_rate:.1f}%

🎯 <b>Аналитика включает:</b>
• Эффективность шаблонов
• Производительность сессий
• Анализ времени отправки
• Сегментация по персонам
• Тренды и прогнозы"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📝 По шаблонам", callback_data="analytics_templates"),
                    InlineKeyboardButton(text="🤖 По сессиям", callback_data="analytics_sessions")
                ],
                [
                    InlineKeyboardButton(text="📅 По времени", callback_data="analytics_time"),
                    InlineKeyboardButton(text="🎭 По персонам", callback_data="analytics_personas")
                ],
                [
                    InlineKeyboardButton(text="📊 Детальный отчет", callback_data="analytics_detailed"),
                    InlineKeyboardButton(text="📋 Экспорт данных", callback_data="analytics_export")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню аналитики: {e}")
        await callback.answer("❌ Ошибка загрузки")