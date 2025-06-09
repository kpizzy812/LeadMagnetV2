# bot/handlers/analytics/analytics.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from storage.database import get_db
from storage.models.base import (
    Conversation, Session, Message, Lead,
    ConversationStatus, MessageRole, FunnelStage
)
from loguru import logger

analytics_router = Router()


@analytics_router.callback_query(F.data == "analytics_main")
async def analytics_main(callback: CallbackQuery):
    """Главное меню аналитики"""

    try:
        # Получаем основные метрики
        stats = await get_analytics_stats()

        text = f"""📈 <b>Аналитика системы</b>

📊 <b>Общая статистика:</b>
• Всего диалогов: {stats['total_conversations']}
• Активных: {stats['active_conversations']}
• Конверсий: {stats['total_conversions']}
• Конверсия: {stats['conversion_rate']:.1f}%

📅 <b>За последние 24 часа:</b>
• Новых диалогов: {stats['new_conversations_24h']}
• Сообщений: {stats['messages_24h']}
• Конверсий: {stats['conversions_24h']}

🕐 <b>Производительность:</b>
• Среднее время ответа: {stats['avg_response_time']:.1f}с
• Активных сессий: {stats['active_sessions']}

⏰ <b>Обновлено:</b> {datetime.now().strftime('%H:%M:%S')}"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 По сессиям", callback_data="analytics_sessions"),
                    InlineKeyboardButton(text="🎭 По персонам", callback_data="analytics_personas")
                ],
                [
                    InlineKeyboardButton(text="📈 Воронка", callback_data="analytics_funnel"),
                    InlineKeyboardButton(text="⏱️ Времени", callback_data="analytics_timing")
                ],
                [
                    InlineKeyboardButton(text="📅 За период", callback_data="analytics_period"),
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_main")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики: {e}")
        await callback.answer("❌ Ошибка загрузки аналитики")


@analytics_router.callback_query(F.data == "analytics_sessions")
async def analytics_sessions(callback: CallbackQuery):
    """Аналитика по сессиям"""

    try:
        async with get_db() as db:
            # Статистика по сессиям
            result = await db.execute(
                select(
                    Session.session_name,
                    Session.persona_type,
                    Session.total_conversations,
                    Session.total_conversions,
                    Session.total_messages_sent,
                    func.count(Conversation.id).label('active_conversations')
                )
                .outerjoin(Conversation, Conversation.session_id == Session.id)
                .where(Conversation.status == ConversationStatus.ACTIVE)
                .group_by(Session.id)
                .order_by(Session.total_conversions.desc())
                .limit(10)
            )
            sessions_stats = result.all()

        if not sessions_stats:
            text = "📊 <b>Статистика по сессиям</b>\n\n📝 Данных пока нет"
        else:
            text = "📊 <b>Топ сессий по конверсиям:</b>\n\n"

            for session in sessions_stats:
                conversion_rate = (session.total_conversions / max(session.total_conversations, 1)) * 100

                text += f"🤖 <code>{session.session_name}</code>\n"
                text += f"   • Персона: {session.persona_type or 'не задана'}\n"
                text += f"   • Диалогов: {session.total_conversations} (активных: {session.active_conversations})\n"
                text += f"   • Конверсий: {session.total_conversions} ({conversion_rate:.1f}%)\n"
                text += f"   • Сообщений: {session.total_messages_sent}\n\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_sessions"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="analytics_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики сессий: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@analytics_router.callback_query(F.data == "analytics_personas")
async def analytics_personas(callback: CallbackQuery):
    """Аналитика по персонам"""

    try:
        async with get_db() as db:
            # Группировка по типам персон
            result = await db.execute(
                select(
                    Session.persona_type,
                    func.count(Session.id).label('sessions_count'),
                    func.sum(Session.total_conversations).label('total_conversations'),
                    func.sum(Session.total_conversions).label('total_conversions'),
                    func.avg(Session.total_conversions / Session.total_conversations.nullif(0) * 100).label(
                        'avg_conversion_rate')
                )
                .where(Session.persona_type.isnot(None))
                .group_by(Session.persona_type)
                .order_by(func.sum(Session.total_conversions).desc())
            )
            personas_stats = result.all()

        if not personas_stats:
            text = "🎭 <b>Статистика по персонам</b>\n\n📝 Данных пока нет"
        else:
            text = "🎭 <b>Эффективность персон:</b>\n\n"

            persona_names = {
                "basic_man": "👨 Простой парень",
                "basic_woman": "👩 Простая девушка",
                "hyip_man": "💼 HYIP мужчина",
                "hyip_woman": "💄 HYIP женщина",
                "investor_man": "📈 Инвестор"
            }

            for persona in personas_stats:
                name = persona_names.get(persona.persona_type, persona.persona_type)
                avg_rate = persona.avg_conversion_rate or 0

                text += f"{name}\n"
                text += f"   • Сессий: {persona.sessions_count}\n"
                text += f"   • Диалогов: {persona.total_conversations or 0}\n"
                text += f"   • Конверсий: {persona.total_conversions or 0}\n"
                text += f"   • Конверсия: {avg_rate:.1f}%\n\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_personas"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="analytics_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики персон: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@analytics_router.callback_query(F.data == "analytics_funnel")
async def analytics_funnel(callback: CallbackQuery):
    """Аналитика воронки продаж"""

    try:
        async with get_db() as db:
            # Распределение по этапам воронки
            result = await db.execute(
                select(
                    Conversation.current_stage,
                    func.count(Conversation.id).label('count')
                )
                .where(Conversation.status == ConversationStatus.ACTIVE)
                .group_by(Conversation.current_stage)
                .order_by(func.count(Conversation.id).desc())
            )
            funnel_stats = result.all()

            # Общее количество конверсий
            conversions_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.ref_link_sent == True)
            )
            total_conversions = conversions_result.scalar() or 0

            # Всего диалогов
            total_result = await db.execute(
                select(func.count(Conversation.id))
            )
            total_conversations = total_result.scalar() or 0

        stage_names = {
            "initial_contact": "🤝 Первый контакт",
            "trust_building": "🤗 Построение доверия",
            "project_inquiry": "❓ Выяснение проектов",
            "interest_qualification": "🎯 Квалификация интереса",
            "presentation": "📢 Презентация",
            "objection_handling": "🛡️ Работа с возражениями",
            "conversion": "💰 Конверсия",
            "post_conversion": "✅ После конверсии"
        }

        text = f"📈 <b>Воронка продаж</b>\n\n"
        text += f"📊 <b>Общая конверсия:</b> {total_conversions}/{total_conversations} "
        text += f"({(total_conversions / max(total_conversations, 1) * 100):.1f}%)\n\n"

        if funnel_stats:
            text += "<b>Распределение по этапам:</b>\n"
            for stage in funnel_stats:
                stage_name = stage_names.get(stage.current_stage, stage.current_stage)
                percentage = (stage.count / max(total_conversations, 1)) * 100
                text += f"{stage_name}: {stage.count} ({percentage:.1f}%)\n"
        else:
            text += "📝 Активных диалогов пока нет"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_funnel"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="analytics_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики воронки: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@analytics_router.callback_query(F.data == "analytics_timing")
async def analytics_timing(callback: CallbackQuery):
    """Аналитика времени ответов"""

    try:
        async with get_db() as db:
            # Средние времена ответов по сессиям
            result = await db.execute(
                select(
                    Session.session_name,
                    func.avg(Conversation.avg_response_time).label('avg_response'),
                    func.min(Conversation.avg_response_time).label('min_response'),
                    func.max(Conversation.avg_response_time).label('max_response')
                )
                .join(Conversation)
                .where(Conversation.avg_response_time > 0)
                .group_by(Session.id)
                .order_by(func.avg(Conversation.avg_response_time))
                .limit(10)
            )
            timing_stats = result.all()

            # Общая статистика времени
            overall_result = await db.execute(
                select(
                    func.avg(Conversation.avg_response_time).label('overall_avg'),
                    func.min(Conversation.avg_response_time).label('overall_min'),
                    func.max(Conversation.avg_response_time).label('overall_max')
                )
                .where(Conversation.avg_response_time > 0)
            )
            overall_stats = overall_result.first()

        text = "⏱️ <b>Анализ времени ответов</b>\n\n"

        if overall_stats and overall_stats.overall_avg:
            text += f"📊 <b>Общая статистика:</b>\n"
            text += f"• Среднее время: {overall_stats.overall_avg:.1f}с\n"
            text += f"• Минимальное: {overall_stats.overall_min:.1f}с\n"
            text += f"• Максимальное: {overall_stats.overall_max:.1f}с\n\n"

            if timing_stats:
                text += "<b>По сессиям (топ быстрых):</b>\n"
                for session in timing_stats:
                    text += f"🤖 <code>{session.session_name}</code>\n"
                    text += f"   • Среднее: {session.avg_response:.1f}с\n"
                    text += f"   • Диапазон: {session.min_response:.1f}с - {session.max_response:.1f}с\n\n"
        else:
            text += "📝 Данных о времени ответов пока нет"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_timing"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="analytics_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики времени: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@analytics_router.callback_query(F.data == "analytics_period")
async def analytics_period(callback: CallbackQuery):
    """Аналитика за период"""

    try:
        # Получаем данные за разные периоды
        periods_data = await get_period_analytics()

        text = f"""📅 <b>Аналитика за периоды</b>

📈 <b>За последние 24 часа:</b>
• Новых диалогов: {periods_data['24h']['new_conversations']}
• Сообщений: {periods_data['24h']['messages']}
• Конверсий: {periods_data['24h']['conversions']}

📊 <b>За последние 7 дней:</b>
• Новых диалогов: {periods_data['7d']['new_conversations']}
• Сообщений: {periods_data['7d']['messages']}
• Конверсий: {periods_data['7d']['conversions']}

📋 <b>За последние 30 дней:</b>
• Новых диалогов: {periods_data['30d']['new_conversations']}
• Сообщений: {periods_data['30d']['messages']}
• Конверсий: {periods_data['30d']['conversions']}

📈 <b>Тренды:</b>
• Рост диалогов: {periods_data['trends']['conversations_growth']:.1f}%
• Рост конверсий: {periods_data['trends']['conversions_growth']:.1f}%"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_period"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="analytics_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики периодов: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


async def get_analytics_stats() -> dict:
    """Получение основной статистики для аналитики"""

    try:
        async with get_db() as db:
            # Общее количество диалогов
            total_conversations_result = await db.execute(
                select(func.count(Conversation.id))
            )
            total_conversations = total_conversations_result.scalar() or 0

            # Активные диалоги
            active_conversations_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.status == ConversationStatus.ACTIVE)
            )
            active_conversations = active_conversations_result.scalar() or 0

            # Общие конверсии
            total_conversions_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.ref_link_sent == True)
            )
            total_conversions = total_conversions_result.scalar() or 0

            # Конверсия
            conversion_rate = (total_conversions / max(total_conversations, 1)) * 100

            # За последние 24 часа
            yesterday = datetime.now() - timedelta(hours=24)

            new_conversations_24h_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.created_at >= yesterday)
            )
            new_conversations_24h = new_conversations_24h_result.scalar() or 0

            messages_24h_result = await db.execute(
                select(func.count(Message.id))
                .where(Message.created_at >= yesterday)
            )
            messages_24h = messages_24h_result.scalar() or 0

            conversions_24h_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.ref_link_sent == True,
                    Conversation.ref_link_sent_at >= yesterday
                )
            )
            conversions_24h = conversions_24h_result.scalar() or 0

            # Среднее время ответа
            avg_response_result = await db.execute(
                select(func.avg(Conversation.avg_response_time))
                .where(Conversation.avg_response_time > 0)
            )
            avg_response_time = avg_response_result.scalar() or 0

            # Активные сессии
            active_sessions_result = await db.execute(
                select(func.count(Session.id))
                .where(Session.status == 'active', Session.ai_enabled == True)
            )
            active_sessions = active_sessions_result.scalar() or 0

            return {
                'total_conversations': total_conversations,
                'active_conversations': active_conversations,
                'total_conversions': total_conversions,
                'conversion_rate': conversion_rate,
                'new_conversations_24h': new_conversations_24h,
                'messages_24h': messages_24h,
                'conversions_24h': conversions_24h,
                'avg_response_time': avg_response_time,
                'active_sessions': active_sessions
            }

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики аналитики: {e}")
        return {
            'total_conversations': 0,
            'active_conversations': 0,
            'total_conversions': 0,
            'conversion_rate': 0,
            'new_conversations_24h': 0,
            'messages_24h': 0,
            'conversions_24h': 0,
            'avg_response_time': 0,
            'active_sessions': 0
        }


async def get_period_analytics() -> dict:
    """Получение аналитики за разные периоды"""

    try:
        async with get_db() as db:
            now = datetime.now()

            periods = {
                '24h': now - timedelta(hours=24),
                '7d': now - timedelta(days=7),
                '30d': now - timedelta(days=30)
            }

            result_data = {
                'trends': {
                    'conversations_growth': 0,
                    'conversions_growth': 0
                }
            }

            for period_name, start_date in periods.items():
                # Новые диалоги
                conversations_result = await db.execute(
                    select(func.count(Conversation.id))
                    .where(Conversation.created_at >= start_date)
                )
                new_conversations = conversations_result.scalar() or 0

                # Сообщения
                messages_result = await db.execute(
                    select(func.count(Message.id))
                    .where(Message.created_at >= start_date)
                )
                messages = messages_result.scalar() or 0

                # Конверсии
                conversions_result = await db.execute(
                    select(func.count(Conversation.id))
                    .where(
                        Conversation.ref_link_sent == True,
                        Conversation.ref_link_sent_at >= start_date
                    )
                )
                conversions = conversions_result.scalar() or 0

                result_data[period_name] = {
                    'new_conversations': new_conversations,
                    'messages': messages,
                    'conversions': conversions
                }

            # Подсчет трендов (сравнение 7д и 30д)
            if result_data['30d']['new_conversations'] > 0:
                week_avg = result_data['7d']['new_conversations'] / 7
                month_avg = result_data['30d']['new_conversations'] / 30
                result_data['trends']['conversations_growth'] = ((week_avg - month_avg) / month_avg) * 100

            if result_data['30d']['conversions'] > 0:
                week_conv_avg = result_data['7d']['conversions'] / 7
                month_conv_avg = result_data['30d']['conversions'] / 30
                result_data['trends']['conversions_growth'] = ((week_conv_avg - month_conv_avg) / month_conv_avg) * 100

            return result_data

    except Exception as e:
        logger.error(f"❌ Ошибка получения периодической аналитики: {e}")
        return {
            '24h': {'new_conversations': 0, 'messages': 0, 'conversions': 0},
            '7d': {'new_conversations': 0, 'messages': 0, 'conversions': 0},
            '30d': {'new_conversations': 0, 'messages': 0, 'conversions': 0},
            'trends': {'conversations_growth': 0, 'conversions_growth': 0}
        }