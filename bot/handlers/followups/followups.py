# bot/handlers/followups/followups.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from storage.database import get_db
from storage.models.base import (
    FollowupSchedule, Conversation, Session, Lead
)
from workflows.followups.scheduler import followup_scheduler
from loguru import logger

followups_router = Router()


@followups_router.callback_query(F.data == "followups_main")
async def followups_main(callback: CallbackQuery):
    """Главное меню фолоуапов"""

    try:
        # Получаем статистику фолоуапов
        stats = await get_followups_stats()

        text = f"""📅 <b>Система фолоуапов</b>

📊 <b>Статистика:</b>
• Ожидающих фолоуапов: {stats['pending']}
• Выполненных сегодня: {stats['executed_today']}
• Всего за неделю: {stats['total_week']}

🔄 <b>Типы фолоуапов:</b>
• 🔔 reminder - напоминание о себе
• 💎 value - полезная информация  
• 📸 proof - социальные доказательства
• 🎯 final - финальное предложение

⏰ <b>Обновлено:</b> {datetime.now().strftime('%H:%M:%S')}"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📋 Ожидающие", callback_data="followups_pending"),
                    InlineKeyboardButton(text="📊 Статистика", callback_data="followups_stats")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="followups_main"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка главного меню фолоуапов: {e}")
        await callback.answer("❌ Ошибка загрузки фолоуапов")


@followups_router.callback_query(F.data == "followups_pending")
async def followups_pending(callback: CallbackQuery):
    """Список ожидающих фолоуапов"""

    try:
        # Получаем ожидающие фолоуапы
        pending_followups = await followup_scheduler.get_pending_followups()

        if not pending_followups:
            text = "📅 <b>Ожидающие фолоуапы</b>\n\n📝 Нет ожидающих фолоуапов"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data="followups_main")
                ]]
            )
        else:
            text = f"📅 <b>Ожидающие фолоуапы ({len(pending_followups)})</b>\n\n"

            # Сортируем по времени выполнения
            pending_followups.sort(key=lambda x: x['time_left'])

            keyboard_buttons = []

            for followup in pending_followups[:10]:  # Показываем первые 10
                time_left = followup['time_left']

                if time_left <= 0:
                    time_str = "⏰ Готов к выполнению"
                elif time_left < 3600:  # Меньше часа
                    time_str = f"⏳ {int(time_left / 60)} мин"
                elif time_left < 86400:  # Меньше дня
                    time_str = f"🕐 {int(time_left / 3600)} ч"
                else:
                    time_str = f"📅 {int(time_left / 86400)} дн"

                type_emoji = {
                    "reminder": "🔔",
                    "value": "💎",
                    "proof": "📸",
                    "final": "🎯"
                }.get(followup['type'], "📝")

                text += f"{type_emoji} {followup['type']} → @{followup['lead_username']}\n"
                text += f"   📱 Сессия: {followup['session_name']}\n"
                text += f"   {time_str}\n\n"

                # Добавляем кнопку для отмены если нужно
                if len(pending_followups) <= 5:  # Показываем кнопки только если мало фолоуапов
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            text=f"❌ Отменить {followup['type']} → @{followup['lead_username'][:10]}",
                            callback_data=f"followup_cancel_{followup['id']}"
                        )
                    ])

            if len(pending_followups) > 10:
                text += f"... и еще {len(pending_followups) - 10} фолоуапов"

            keyboard_buttons.append([
                InlineKeyboardButton(text="🔄 Обновить", callback_data="followups_pending"),
                InlineKeyboardButton(text="🔙 Назад", callback_data="followups_main")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка списка ожидающих фолоуапов: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@followups_router.callback_query(F.data.startswith("followup_cancel_"))
async def followup_cancel(callback: CallbackQuery):
    """Отмена фолоуапа"""

    try:
        followup_id = int(callback.data.split("_")[-1])

        success = await followup_scheduler.cancel_followup(followup_id)

        if success:
            await callback.answer("✅ Фолоуап отменен")
            # Обновляем список
            await followups_pending(callback)
        else:
            await callback.answer("❌ Ошибка отмены фолоуапа")

    except Exception as e:
        logger.error(f"❌ Ошибка отмены фолоуапа: {e}")
        await callback.answer("❌ Ошибка отмены")


@followups_router.callback_query(F.data == "followups_stats")
async def followups_stats(callback: CallbackQuery):
    """Детальная статистика фолоуапов"""

    try:
        async with get_db() as db:
            # Статистика по типам
            type_stats_result = await db.execute(
                select(
                    FollowupSchedule.followup_type,
                    func.count(FollowupSchedule.id).label('total'),
                    func.sum(
                        case(
                            (FollowupSchedule.executed == True, 1),
                            else_=0
                        )
                    ).label('executed')
                )
                .group_by(FollowupSchedule.followup_type)
                .order_by(func.count(FollowupSchedule.id).desc())
            )
            type_stats = type_stats_result.all()

            # Статистика за последние дни
            today = datetime.now().date()

            stats_periods = []
            for days_ago in range(7):
                date = today - timedelta(days=days_ago)

                executed_result = await db.execute(
                    select(func.count(FollowupSchedule.id))
                    .where(
                        FollowupSchedule.executed == True,
                        func.date(FollowupSchedule.executed_at) == date
                    )
                )
                executed = executed_result.scalar() or 0

                stats_periods.append({
                    'date': date,
                    'executed': executed
                })

        text = "📊 <b>Детальная статистика фолоуапов</b>\n\n"

        # Статистика по типам
        if type_stats:
            text += "<b>📈 По типам фолоуапов:</b>\n"

            type_names = {
                "reminder": "🔔 Напоминания",
                "value": "💎 Ценность",
                "proof": "📸 Доказательства",
                "final": "🎯 Финальные"
            }

            for stat in type_stats:
                type_name = type_names.get(stat.followup_type, stat.followup_type)
                executed = stat.executed or 0
                total = stat.total or 1
                success_rate = (executed / total) * 100

                text += f"{type_name}: {executed}/{total} ({success_rate:.1f}%)\n"

            text += "\n"

        # Статистика по дням
        text += "<b>📅 За последние 7 дней:</b>\n"
        for period in stats_periods:
            date_str = period['date'].strftime('%d.%m')
            text += f"{date_str}: {period['executed']} выполнено\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="followups_stats"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="followups_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка статистики фолоуапов: {e}")
        await callback.answer("❌ Ошибка загрузки статистики")


async def get_followups_stats() -> dict:
    """Получение статистики фолоуапов"""

    try:
        async with get_db() as db:
            # Ожидающие фолоуапы
            pending_result = await db.execute(
                select(func.count(FollowupSchedule.id))
                .where(FollowupSchedule.executed == False)
            )
            pending = pending_result.scalar() or 0

            # Выполненные сегодня
            today = datetime.now().date()
            executed_today_result = await db.execute(
                select(func.count(FollowupSchedule.id))
                .where(
                    FollowupSchedule.executed == True,
                    func.date(FollowupSchedule.executed_at) == today
                )
            )
            executed_today = executed_today_result.scalar() or 0

            # Всего за неделю
            week_ago = datetime.now().date() - timedelta(days=7)
            total_week_result = await db.execute(
                select(func.count(FollowupSchedule.id))
                .where(
                    FollowupSchedule.executed == True,
                    func.date(FollowupSchedule.executed_at) >= week_ago
                )
            )
            total_week = total_week_result.scalar() or 0

            return {
                'pending': pending,
                'executed_today': executed_today,
                'total_week': total_week
            }

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики фолоуапов: {e}")
        return {
            'pending': 0,
            'executed_today': 0,
            'total_week': 0
        }