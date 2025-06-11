# bot/handlers/dashboard/dashboard.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from storage.database import get_db
from storage.models.base import Conversation, Session, Message as DBMessage, ConversationStatus
from sqlalchemy import select, func
from loguru import logger

dashboard_router = Router()


@dashboard_router.message(Command("start"))
async def cmd_start(message: Message):
    """Главное меню бота"""

    # Получаем основную статистику
    stats = await get_dashboard_stats()

    text = f"""🎯 <b>Lead Management System</b>

📊 <b>Статистика:</b>
• Активных диалогов: {stats['active_conversations']}
• Всего сессий: {stats['total_sessions']}
• Сообщений сегодня: {stats['messages_today']}
• Конверсий сегодня: {stats['conversions_today']}
• Ожидающих фолоуапов: {stats['pending_followups']}

📤 <b>Cold Outreach:</b>
• Активных кампаний: {stats['active_campaigns']}
• Отправлено сегодня: {stats['outreach_sent_today']}

⏰ <b>Последнее обновление:</b> {datetime.now().strftime('%H:%M:%S')}"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Сессии", callback_data="sessions_list"),
                InlineKeyboardButton(text="💬 Диалоги", callback_data="dialogs_list")
            ],
            [
                InlineKeyboardButton(text="📈 Аналитика", callback_data="analytics_main"),
                InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast_main")
            ],
            [
                InlineKeyboardButton(text="📅 Фолоуапы", callback_data="followups_main"),
                InlineKeyboardButton(text="🤖 Управление ИИ", callback_data="ai_control_main")
            ],
            [
                InlineKeyboardButton(text="📤 Cold Outreach", callback_data="outreach_main"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="dashboard_refresh")
            ]
        ]
    )

    await message.answer(text, reply_markup=keyboard)


@dashboard_router.callback_query(F.data == "dashboard_refresh")
async def refresh_dashboard(callback: CallbackQuery):
    """Обновление дашборда"""

    stats = await get_dashboard_stats()

    text = f"""🎯 <b>Lead Management System</b>

📊 <b>Статистика:</b>
• Активных диалогов: {stats['active_conversations']}
• Всего сессий: {stats['total_sessions']}
• Сообщений сегодня: {stats['messages_today']}
• Конверсий сегодня: {stats['conversions_today']}
• Ожидающих фолоуапов: {stats['pending_followups']}

📤 <b>Cold Outreach:</b>
• Активных кампаний: {stats['active_campaigns']}
• Отправлено сегодня: {stats['outreach_sent_today']}

⏰ <b>Последнее обновление:</b> {datetime.now().strftime('%H:%M:%S')}"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Сессии", callback_data="sessions_list"),
                InlineKeyboardButton(text="💬 Диалоги", callback_data="dialogs_list")
            ],
            [
                InlineKeyboardButton(text="📈 Аналитика", callback_data="analytics_main"),
                InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast_main")
            ],
            [
                InlineKeyboardButton(text="📅 Фолоуапы", callback_data="followups_main"),
                InlineKeyboardButton(text="🤖 Управление ИИ", callback_data="ai_control_main")
            ],
            [
                InlineKeyboardButton(text="📤 Cold Outreach", callback_data="outreach_main"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="dashboard_refresh")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer("✅ Обновлено")


async def get_dashboard_stats() -> dict:
    """Получение статистики для дашборда"""

    try:
        async with get_db() as db:
            # Активные диалоги
            active_conversations_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.status == ConversationStatus.ACTIVE)
            )
            active_conversations = active_conversations_result.scalar() or 0

            # Всего сессий
            total_sessions_result = await db.execute(
                select(func.count(Session.id))
            )
            total_sessions = total_sessions_result.scalar() or 0

            # Сообщения сегодня
            today = datetime.now().date()
            messages_today_result = await db.execute(
                select(func.count(DBMessage.id))
                .where(func.date(DBMessage.created_at) == today)
            )
            messages_today = messages_today_result.scalar() or 0

            # Конверсии сегодня (диалоги где отправлена реф ссылка)
            conversions_today_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.ref_link_sent == True,
                    func.date(Conversation.ref_link_sent_at) == today
                )
            )
            conversions_today = conversions_today_result.scalar() or 0

            # Ожидающие фолоуапы
            from storage.models.base import FollowupSchedule
            pending_followups_result = await db.execute(
                select(func.count(FollowupSchedule.id))
                .where(FollowupSchedule.executed == False)
            )
            pending_followups = pending_followups_result.scalar() or 0

            # НОВОЕ: Статистика Cold Outreach
            try:
                from storage.models.cold_outreach import OutreachCampaign, OutreachMessage, CampaignStatus

                # Активные кампании
                active_campaigns_result = await db.execute(
                    select(func.count(OutreachCampaign.id))
                    .where(OutreachCampaign.status == CampaignStatus.ACTIVE)
                )
                active_campaigns = active_campaigns_result.scalar() or 0

                # Отправлено сегодня
                outreach_sent_today_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(func.date(OutreachMessage.sent_at) == today)
                )
                outreach_sent_today = outreach_sent_today_result.scalar() or 0

            except Exception as e:
                logger.warning(f"⚠️ Cold Outreach модели недоступны: {e}")
                active_campaigns = 0
                outreach_sent_today = 0

            return {
                'active_conversations': active_conversations,
                'total_sessions': total_sessions,
                'messages_today': messages_today,
                'conversions_today': conversions_today,
                'pending_followups': pending_followups,
                'active_campaigns': active_campaigns,
                'outreach_sent_today': outreach_sent_today
            }

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики дашборда: {e}")
        return {
            'active_conversations': 0,
            'total_sessions': 0,
            'messages_today': 0,
            'conversions_today': 0,
            'pending_followups': 0,
            'active_campaigns': 0,
            'outreach_sent_today': 0
        }