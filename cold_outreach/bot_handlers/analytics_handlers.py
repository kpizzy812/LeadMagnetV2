# cold_outreach/bot_handlers/analytics_handlers.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from typing import Dict, List, Any

from storage.database import get_db
from storage.models.cold_outreach import (
    OutreachCampaign, OutreachMessage, OutreachTemplate,
    OutreachLead, OutreachMessageStatus
)
from sqlalchemy import select, func, and_, desc
from loguru import logger

analytics_handlers_router = Router()


@analytics_handlers_router.callback_query(F.data == "analytics_templates")
async def analytics_templates(callback: CallbackQuery):
    """Аналитика по шаблонам"""

    try:
        async with get_db() as db:
            # Получаем статистику по шаблонам
            template_stats_query = """
            SELECT 
                ot.id,
                ot.name,
                ot.usage_count,
                COUNT(om.id) as total_sent,
                COUNT(CASE WHEN om.status = 'sent' THEN 1 END) as successful_sent,
                COUNT(CASE WHEN om.got_response = true THEN 1 END) as responses,
                COUNT(CASE WHEN om.converted = true THEN 1 END) as conversions,
                AVG(CASE WHEN om.response_time IS NOT NULL THEN om.response_time END) as avg_response_time
            FROM outreach_templates ot
            LEFT JOIN outreach_messages om ON ot.id = om.template_id
            WHERE ot.is_active = true
            GROUP BY ot.id, ot.name, ot.usage_count
            ORDER BY total_sent DESC
            LIMIT 10
            """

            result = await db.execute(template_stats_query)
            template_stats = result.fetchall()

        if not template_stats:
            text = """📝 <b>Аналитика по шаблонам</b>

📊 Нет данных по использованию шаблонов.

Создайте кампании с шаблонами для получения статистики."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📝 Шаблоны", callback_data="outreach_templates"),
                        InlineKeyboardButton(text="🚀 Кампании", callback_data="outreach_campaigns")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                    ]
                ]
            )
        else:
            text = f"📝 <b>Топ шаблонов по эффективности</b>\n\n"

            keyboard_buttons = []

            for stats in template_stats:
                template_id, name, usage_count, total_sent, successful_sent, responses, conversions, avg_response_time = stats

                # Рассчитываем метрики
                delivery_rate = (successful_sent / max(total_sent, 1)) * 100
                response_rate = (responses / max(successful_sent, 1)) * 100
                conversion_rate = (conversions / max(successful_sent, 1)) * 100

                text += f"📝 <b>{name}</b>\n"
                text += f"   📤 Отправлено: {total_sent} (доставлено: {delivery_rate:.1f}%)\n"
                text += f"   💬 Ответов: {responses} ({response_rate:.1f}%)\n"
                text += f"   🎯 Конверсий: {conversions} ({conversion_rate:.1f}%)\n"

                if avg_response_time:
                    hours = int(avg_response_time // 3600)
                    text += f"   ⏱️ Среднее время ответа: {hours}ч\n"

                text += "\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📊 {name[:20]}... ({response_rate:.1f}%)",
                        callback_data=f"analytics_template_detail_{template_id}"
                    )
                ])

            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="📈 Сравнить шаблоны", callback_data="analytics_templates_compare"),
                    InlineKeyboardButton(text="📊 Экспорт данных", callback_data="analytics_templates_export")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_templates"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики шаблонов: {e}")
        await callback.answer("❌ Ошибка загрузки аналитики")


@analytics_handlers_router.callback_query(F.data.startswith("analytics_template_detail_"))
async def analytics_template_detail(callback: CallbackQuery):
    """Детальная аналитика по шаблону"""

    try:
        template_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            # Получаем детальную статистику шаблона
            template_result = await db.execute(
                select(OutreachTemplate).where(OutreachTemplate.id == template_id)
            )
            template = template_result.scalar_one_or_none()

            if not template:
                await callback.answer("❌ Шаблон не найден")
                return

            # Статистика за последние 30 дней
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)

            # Общая статистика
            total_sent_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.template_id == template_id,
                    OutreachMessage.sent_at >= thirty_days_ago
                )
            )
            total_sent = total_sent_result.scalar() or 0

            # Успешно доставленные
            delivered_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.template_id == template_id,
                    OutreachMessage.status == OutreachMessageStatus.SENT,
                    OutreachMessage.sent_at >= thirty_days_ago
                )
            )
            delivered = delivered_result.scalar() or 0

            # Получили ответ
            responses_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.template_id == template_id,
                    OutreachMessage.got_response == True,
                    OutreachMessage.sent_at >= thirty_days_ago
                )
            )
            responses = responses_result.scalar() or 0

            # Конверсии
            conversions_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.template_id == template_id,
                    OutreachMessage.converted == True,
                    OutreachMessage.sent_at >= thirty_days_ago
                )
            )
            conversions = conversions_result.scalar() or 0

            # Статистика по статусам ошибок
            error_stats_result = await db.execute(
                select(
                    OutreachMessage.error_code,
                    func.count(OutreachMessage.id).label('count')
                )
                .where(
                    OutreachMessage.template_id == template_id,
                    OutreachMessage.status.in_([
                        OutreachMessageStatus.FAILED,
                        OutreachMessageStatus.BLOCKED,
                        OutreachMessageStatus.FLOOD_WAIT
                    ]),
                    OutreachMessage.sent_at >= thirty_days_ago
                )
                .group_by(OutreachMessage.error_code)
                .order_by(desc(func.count(OutreachMessage.id)))
            )
            error_stats = error_stats_result.fetchall()

        # Рассчитываем метрики
        delivery_rate = (delivered / max(total_sent, 1)) * 100
        response_rate = (responses / max(delivered, 1)) * 100
        conversion_rate = (conversions / max(delivered, 1)) * 100

        text = f"""📝 <b>Детальная аналитика: {template.name}</b>

📊 <b>Статистика за 30 дней:</b>
• Отправлено: {total_sent}
• Доставлено: {delivered} ({delivery_rate:.1f}%)
• Получено ответов: {responses} ({response_rate:.1f}%)
• Конверсий: {conversions} ({conversion_rate:.1f}%)

🎯 <b>Эффективность:</b>
• Общая конверсия: {(conversions / max(total_sent, 1)) * 100:.2f}%
• Время ответа: {template.avg_response_time or 'N/A'}

📝 <b>Содержание шаблона:</b>
<code>{template.text[:200]}{'...' if len(template.text) > 200 else ''}</code>"""

        if error_stats:
            text += "\n\n❌ <b>Основные ошибки:</b>\n"
            for error_code, count in error_stats[:3]:
                text += f"• {error_code or 'Unknown'}: {count}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📈 Динамика по дням",
                                         callback_data=f"analytics_template_timeline_{template_id}"),
                    InlineKeyboardButton(text="🔧 Улучшения", callback_data=f"template_suggestions_{template_id}")
                ],
                [
                    InlineKeyboardButton(text="📝 К шаблону", callback_data=f"template_view_{template_id}"),
                    InlineKeyboardButton(text="📊 Все шаблоны", callback_data="analytics_templates")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка детальной аналитики шаблона: {e}")
        await callback.answer("❌ Ошибка загрузки")


@analytics_handlers_router.callback_query(F.data == "analytics_sessions")
async def analytics_sessions(callback: CallbackQuery):
    """Аналитика по сессиям"""

    try:
        from cold_outreach.core.outreach_manager import outreach_manager

        # Получаем статистику сессий
        session_stats = await outreach_manager.get_session_outreach_stats()

        if not session_stats:
            text = """🤖 <b>Аналитика по сессиям</b>

📊 Нет активных сессий для анализа."""

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]]
            )
        else:
            # Сортируем сессии по эффективности
            sessions_list = []
            for session_name, stats in session_stats.items():
                daily_sent = stats.get("daily_sent", 0)
                daily_limit = stats.get("daily_limit", 1)
                efficiency = (daily_sent / daily_limit) * 100 if daily_limit > 0 else 0

                sessions_list.append({
                    "name": session_name,
                    "stats": stats,
                    "efficiency": efficiency
                })

            sessions_list.sort(key=lambda x: x["efficiency"], reverse=True)

            text = f"🤖 <b>Аналитика по сессиям ({len(sessions_list)})</b>\n\n"

            keyboard_buttons = []

            for session_data in sessions_list[:10]:  # Топ 10
                session_name = session_data["name"]
                stats = session_data["stats"]
                efficiency = session_data["efficiency"]

                mode_emoji = "📤" if stats.get("mode") == "outreach" else "💬"
                status_emoji = "🚫" if stats.get("is_blocked") else "✅"
                premium_emoji = "💎" if stats.get("is_premium") else "📱"

                daily_sent = stats.get("daily_sent", 0)
                daily_limit = stats.get("daily_limit", 0)
                total_messages = stats.get("total_messages", 0)

                text += f"{mode_emoji}{status_emoji}{premium_emoji} <b>{session_name}</b>\n"
                text += f"   📊 Эффективность: {efficiency:.1f}%\n"
                text += f"   📤 Сегодня: {daily_sent}/{daily_limit}\n"
                text += f"   📈 Всего: {total_messages}\n\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"{mode_emoji} {session_name[:15]}... ({efficiency:.0f}%)",
                        callback_data=f"analytics_session_detail_{session_name}"
                    )
                ])

            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_sessions"),
                    InlineKeyboardButton(text="⚙️ Управление", callback_data="outreach_sessions")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики сессий: {e}")
        await callback.answer("❌ Ошибка загрузки аналитики")


@analytics_handlers_router.callback_query(F.data.startswith("analytics_session_detail_"))
async def analytics_session_detail(callback: CallbackQuery):
    """Детальная аналитика по сессии"""

    try:
        session_name = callback.data.replace("analytics_session_detail_", "")

        async with get_db() as db:
            # Статистика за последние 7 дней
            seven_days_ago = datetime.utcnow() - timedelta(days=7)

            # Сообщения по дням
            daily_stats_result = await db.execute(
                select(
                    func.date(OutreachMessage.sent_at).label('date'),
                    func.count(OutreachMessage.id).label('total'),
                    func.count(
                        func.nullif(OutreachMessage.status != OutreachMessageStatus.SENT, True)
                    ).label('successful'),
                    func.count(
                        func.nullif(OutreachMessage.got_response != True, True)
                    ).label('responses')
                )
                .where(
                    OutreachMessage.session_name == session_name,
                    OutreachMessage.sent_at >= seven_days_ago
                )
                .group_by(func.date(OutreachMessage.sent_at))
                .order_by(func.date(OutreachMessage.sent_at))
            )
            daily_stats = daily_stats_result.fetchall()

            # Общая статистика
            total_result = await db.execute(
                select(func.count(OutreachMessage.id))
                .where(OutreachMessage.session_name == session_name)
            )
            total_messages = total_result.scalar() or 0

            # Сессия сейчас
            from cold_outreach.core.outreach_manager import outreach_manager
            session_stats = await outreach_manager.get_session_outreach_stats()
            current_stats = session_stats.get(session_name, {})

        text = f"""🤖 <b>Детальная аналитика: {session_name}</b>

📊 <b>Текущий статус:</b>
• Режим: {current_stats.get('mode', 'unknown')}
• Статус: {'🚫 Заблокирован' if current_stats.get('is_blocked') else '✅ Активен'}
• Тип: {'💎 Premium' if current_stats.get('is_premium') else '📱 Обычный'}

📈 <b>Активность сегодня:</b>
• Отправлено: {current_stats.get('daily_sent', 0)}/{current_stats.get('daily_limit', 0)}
• Активных диалогов: {current_stats.get('active_dialogs', 0)}

📊 <b>Статистика за 7 дней:</b>"""

        if daily_stats:
            total_week = sum(stat.total for stat in daily_stats)
            successful_week = sum(stat.successful for stat in daily_stats)
            responses_week = sum(stat.responses for stat in daily_stats)

            text += f"""
• Отправлено: {total_week}
• Доставлено: {successful_week} ({(successful_week / max(total_week, 1)) * 100:.1f}%)
• Ответов: {responses_week} ({(responses_week / max(successful_week, 1)) * 100:.1f}%)

📅 <b>По дням:</b>"""

            for stat in daily_stats[-5:]:  # Последние 5 дней
                date_str = stat.date.strftime('%d.%m')
                success_rate = (stat.successful / max(stat.total, 1)) * 100
                text += f"\n• {date_str}: {stat.total} ({success_rate:.0f}% доставка)"
        else:
            text += "\nНет данных за последние 7 дней"

        text += f"\n\n🎯 <b>Всего сообщений:</b> {total_messages}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"session_settings_{session_name}"),
                    InlineKeyboardButton(text="🔄 Перезапуск", callback_data=f"session_restart_{session_name}")
                ],
                [
                    InlineKeyboardButton(text="📊 Все сессии", callback_data="analytics_sessions"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка детальной аналитики сессии: {e}")
        await callback.answer("❌ Ошибка загрузки")


@analytics_handlers_router.callback_query(F.data == "analytics_time")
async def analytics_time(callback: CallbackQuery):
    """Аналитика по времени отправки"""

    try:
        async with get_db() as db:
            # Статистика по часам за последние 7 дней
            seven_days_ago = datetime.utcnow() - timedelta(days=7)

            hourly_stats_result = await db.execute(
                select(
                    func.extract('hour', OutreachMessage.sent_at).label('hour'),
                    func.count(OutreachMessage.id).label('total'),
                    func.count(
                        func.nullif(OutreachMessage.got_response != True, True)
                    ).label('responses')
                )
                .where(
                    OutreachMessage.sent_at >= seven_days_ago,
                    OutreachMessage.status == OutreachMessageStatus.SENT
                )
                .group_by(func.extract('hour', OutreachMessage.sent_at))
                .order_by(func.extract('hour', OutreachMessage.sent_at))
            )
            hourly_stats = hourly_stats_result.fetchall()

            # Статистика по дням недели
            weekday_stats_result = await db.execute(
                select(
                    func.extract('dow', OutreachMessage.sent_at).label('weekday'),
                    func.count(OutreachMessage.id).label('total'),
                    func.count(
                        func.nullif(OutreachMessage.got_response != True, True)
                    ).label('responses')
                )
                .where(
                    OutreachMessage.sent_at >= seven_days_ago,
                    OutreachMessage.status == OutreachMessageStatus.SENT
                )
                .group_by(func.extract('dow', OutreachMessage.sent_at))
                .order_by(func.extract('dow', OutreachMessage.sent_at))
            )
            weekday_stats = weekday_stats_result.fetchall()

        text = "⏰ <b>Аналитика по времени отправки</b>\n\n"

        if hourly_stats:
            text += "🕐 <b>Эффективность по часам:</b>\n"

            # Находим лучшие часы
            best_hours = []
            for stat in hourly_stats:
                hour = int(stat.hour)
                response_rate = (stat.responses / max(stat.total, 1)) * 100
                best_hours.append((hour, response_rate, stat.total))

            best_hours.sort(key=lambda x: x[1], reverse=True)

            for hour, response_rate, total in best_hours[:5]:
                text += f"• {hour:02d}:00 - {response_rate:.1f}% ответов ({total} отправок)\n"

        if weekday_stats:
            text += "\n📅 <b>Эффективность по дням недели:</b>\n"

            weekday_names = {
                0: "Воскресенье", 1: "Понедельник", 2: "Вторник",
                3: "Среда", 4: "Четверг", 5: "Пятница", 6: "Суббота"
            }

            weekday_data = []
            for stat in weekday_stats:
                day_name = weekday_names.get(int(stat.weekday), "Unknown")
                response_rate = (stat.responses / max(stat.total, 1)) * 100
                weekday_data.append((day_name, response_rate, stat.total))

            weekday_data.sort(key=lambda x: x[1], reverse=True)

            for day_name, response_rate, total in weekday_data:
                text += f"• {day_name}: {response_rate:.1f}% ответов ({total} отправок)\n"

        text += "\n💡 <b>Рекомендации:</b>\n"
        if hourly_stats:
            best_hour = max(hourly_stats, key=lambda x: (x.responses / max(x.total, 1)))
            text += f"• Лучший час для отправки: {int(best_hour.hour):02d}:00\n"

        if weekday_stats:
            best_day = max(weekday_stats, key=lambda x: (x.responses / max(x.total, 1)))
            day_name = weekday_names.get(int(best_day.weekday), "Unknown")
            text += f"• Лучший день: {day_name}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Подробная статистика", callback_data="analytics_time_detailed"),
                    InlineKeyboardButton(text="⚙️ Настроить время", callback_data="analytics_time_settings")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_time"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка аналитики по времени: {e}")
        await callback.answer("❌ Ошибка загрузки аналитики")


@analytics_handlers_router.callback_query(F.data == "analytics_detailed")
async def analytics_detailed(callback: CallbackQuery):
    """Детальный отчет по всей системе"""

    try:
        async with get_db() as db:
            # Общая статистика за разные периоды
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)
            week_ago = now - timedelta(days=7)
            month_ago = now - timedelta(days=30)

            periods = {
                "24ч": yesterday,
                "7д": week_ago,
                "30д": month_ago
            }

            report_data = {}

            for period_name, start_date in periods.items():
                # Общие отправки
                total_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(OutreachMessage.sent_at >= start_date)
                )
                total = total_result.scalar() or 0

                # Успешные
                successful_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(
                        OutreachMessage.sent_at >= start_date,
                        OutreachMessage.status == OutreachMessageStatus.SENT
                    )
                )
                successful = successful_result.scalar() or 0

                # Ответы
                responses_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(
                        OutreachMessage.sent_at >= start_date,
                        OutreachMessage.got_response == True
                    )
                )
                responses = responses_result.scalar() or 0

                # Конверсии
                conversions_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(
                        OutreachMessage.sent_at >= start_date,
                        OutreachMessage.converted == True
                    )
                )
                conversions = conversions_result.scalar() or 0

                report_data[period_name] = {
                    "total": total,
                    "successful": successful,
                    "responses": responses,
                    "conversions": conversions,
                    "delivery_rate": (successful / max(total, 1)) * 100,
                    "response_rate": (responses / max(successful, 1)) * 100,
                    "conversion_rate": (conversions / max(successful, 1)) * 100
                }

            # Активные кампании
            active_campaigns_result = await db.execute(
                select(func.count(OutreachCampaign.id))
                .where(OutreachCampaign.status == "active")
            )
            active_campaigns = active_campaigns_result.scalar() or 0

            # Топ ошибки
            errors_result = await db.execute(
                select(
                    OutreachMessage.error_code,
                    func.count(OutreachMessage.id).label('count')
                )
                .where(
                    OutreachMessage.sent_at >= week_ago,
                    OutreachMessage.error_code.isnot(None)
                )
                .group_by(OutreachMessage.error_code)
                .order_by(desc(func.count(OutreachMessage.id)))
                .limit(5)
            )
            top_errors = errors_result.fetchall()

        text = f"""📊 <b>Детальный отчет системы</b>

🚀 <b>Активные кампании:</b> {active_campaigns}

📈 <b>Статистика по периодам:</b>"""

        for period_name, data in report_data.items():
            text += f"""

📅 <b>За {period_name}:</b>
• Отправлено: {data['total']}
• Доставлено: {data['successful']} ({data['delivery_rate']:.1f}%)
• Ответов: {data['responses']} ({data['response_rate']:.1f}%)
• Конверсий: {data['conversions']} ({data['conversion_rate']:.1f}%)"""

        if top_errors:
            text += "\n\n❌ <b>Топ ошибок за 7 дней:</b>\n"
            for error_code, count in top_errors:
                text += f"• {error_code or 'Unknown'}: {count}\n"

        # Вычисляем тренды
        if report_data["24ч"]["total"] > 0 and report_data["7д"]["total"] > 0:
            daily_avg_week = report_data["7д"]["total"] / 7
            daily_yesterday = report_data["24ч"]["total"]
            trend = "📈" if daily_yesterday > daily_avg_week else "📉"
            text += f"\n\n{trend} <b>Тренд:</b> "
            text += f"Вчера {daily_yesterday} vs среднее {daily_avg_week:.1f}/день"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📋 Экспорт отчета", callback_data="analytics_export_detailed"),
                    InlineKeyboardButton(text="📧 Отправить на email", callback_data="analytics_email_report")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="analytics_detailed"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка детального отчета: {e}")
        await callback.answer("❌ Ошибка генерации отчета")


@analytics_handlers_router.callback_query(F.data == "analytics_export")
async def analytics_export(callback: CallbackQuery):
    """Экспорт данных аналитики"""

    try:
        text = """📋 <b>Экспорт данных аналитики</b>

Выберите формат и данные для экспорта:

🔹 <b>Доступные форматы:</b>
• CSV - для анализа в Excel
• JSON - для разработчиков
• Текстовый отчет - для просмотра

🔹 <b>Доступные данные:</b>
• Статистика кампаний
• Эффективность шаблонов  
• Производительность сессий
• Временная аналитика"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 CSV отчет", callback_data="analytics_export_csv"),
                    InlineKeyboardButton(text="📋 JSON данные", callback_data="analytics_export_json")
                ],
                [
                    InlineKeyboardButton(text="📄 Текстовый отчет", callback_data="analytics_export_text"),
                    InlineKeyboardButton(text="📧 Email отчет", callback_data="analytics_export_email")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка экспорта: {e}")
        await callback.answer("❌ Ошибка экспорта")


@analytics_handlers_router.callback_query(F.data.startswith("analytics_export_"))
async def analytics_export_format(callback: CallbackQuery):
    """Обработка экспорта в конкретном формате"""

    try:
        export_format = callback.data.split("_")[-1]

        # Пока показываем заглушку
        text = f"""📋 <b>Экспорт в формате {export_format.upper()}</b>

⚠️ <b>Функция в разработке</b>

Данная функция будет доступна в следующем обновлении системы.

Пока вы можете:
• Просматривать аналитику в интерфейсе
• Делать скриншоты отчетов
• Копировать данные вручную"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Просмотр аналитики", callback_data="analytics_detailed")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="analytics_export")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка экспорта формата: {e}")
        await callback.answer("❌ Ошибка экспорта")


# Дополнительные обработчики

@analytics_handlers_router.callback_query(F.data == "analytics_personas")
async def analytics_personas(callback: CallbackQuery):
    """Аналитика по персонам (заглушка)"""

    text = """🎭 <b>Аналитика по персонам</b>

⚠️ <b>Функция в разработке</b>

Здесь будет отображаться:
• Эффективность разных типов персон
• Конверсия по персонам
• Сравнение результатов
• Рекомендации по выбору персоны"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="outreach_analytics")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@analytics_handlers_router.callback_query(F.data.startswith("analytics_template_timeline_"))
async def analytics_template_timeline(callback: CallbackQuery):
    """Временная динамика шаблона (заглушка)"""

    template_id = callback.data.split("_")[-1]

    text = f"""📈 <b>Динамика шаблона по дням</b>

⚠️ <b>Функция в разработке</b>

Здесь будет график эффективности шаблона по дням:
• Количество отправок
• Процент ответов  
• Тренды эффективности
• Сравнение с другими шаблонами"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 К шаблону", callback_data=f"analytics_template_detail_{template_id}")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="analytics_templates")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
