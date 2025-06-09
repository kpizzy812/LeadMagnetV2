# bot/handlers/dialogs.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import Conversation, Lead, Session, Message as DBMessage
from loguru import logger

dialogs_router = Router()


@dialogs_router.callback_query(F.data == "dialogs_list")
async def dialogs_list(callback: CallbackQuery):
    """Список всех диалогов"""

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .order_by(Conversation.updated_at.desc())
                .limit(15)
            )
            conversations = result.scalars().all()

        if not conversations:
            await callback.message.edit_text(
                "💬 Диалогов пока нет",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                    ]]
                )
            )
            return

        text = "💬 <b>Активные диалоги:</b>\n\n"
        keyboard_buttons = []

        for conv in conversations:
            status_emoji = {
                "active": "🟢",
                "paused": "⏸️",
                "completed": "✅",
                "blocked": "🔴"
            }.get(conv.status, "❓")

            ref_emoji = "🔗" if conv.ref_link_sent else "📝"

            text += f"{status_emoji} {ref_emoji} @{conv.lead.username} ↔ {conv.session.session_name}\n"
            text += f"   • Этап: {conv.current_stage}\n"
            text += f"   • Сообщений: {conv.messages_count}\n\n"

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"👤 {conv.lead.username}",
                    callback_data=f"dialog_view_{conv.id}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data="dialogs_list")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки диалогов: {e}")
        await callback.answer("❌ Ошибка загрузки диалогов")


@dialogs_router.callback_query(F.data.startswith("dialog_view_"))
async def dialog_view(callback: CallbackQuery):
    """Просмотр конкретного диалога"""

    try:
        conv_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conv_id)
            )
            conversation = result.scalar_one_or_none()

        if not conversation:
            await callback.answer("❌ Диалог не найден")
            return

        # Статистика диалога
        text = f"""💬 <b>Диалог с @{conversation.lead.username}</b>

👤 <b>Лид:</b> @{conversation.lead.username}
🤖 <b>Сессия:</b> {conversation.session.session_name}
🎭 <b>Персона:</b> {conversation.session.persona_type or 'не задана'}

📊 <b>Статус:</b> {conversation.status}
🎯 <b>Этап:</b> {conversation.current_stage}
🔗 <b>Реф ссылка:</b> {'✅ отправлена' if conversation.ref_link_sent else '❌ не отправлена'}

📈 <b>Статистика:</b>
• Всего сообщений: {conversation.messages_count}
• От пользователя: {conversation.user_messages_count}
• От ассистента: {conversation.assistant_messages_count}

📅 <b>Создан:</b> {conversation.created_at.strftime('%d.%m.%Y %H:%M')}
🕐 <b>Обновлен:</b> {conversation.updated_at.strftime('%d.%m.%Y %H:%M')}"""

        # Последние сообщения
        if conversation.messages:
            text += "\n\n📝 <b>Последние сообщения:</b>\n"
            for msg in conversation.messages[-5:]:  # Последние 5 сообщений
                role_emoji = "👤" if msg.role == "user" else "🤖"
                time_str = msg.created_at.strftime('%H:%M')
                content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
                text += f"{role_emoji} [{time_str}] {content_preview}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Написать",
                        callback_data=f"dialog_send_{conv_id}"
                    ),
                    InlineKeyboardButton(
                        text="🤖 ИИ вкл/выкл",
                        callback_data=f"dialog_toggle_ai_{conv_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📈 Аналитика",
                        callback_data=f"dialog_analytics_{conv_id}"
                    ),
                    InlineKeyboardButton(
                        text="🗑️ Удалить",
                        callback_data=f"dialog_delete_{conv_id}"
                    )
                ],
                [
                    InlineKeyboardButton(text="🔙 К списку", callback_data="dialogs_list")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка просмотра диалога: {e}")
        await callback.answer("❌ Ошибка загрузки диалога")


@dialogs_router.callback_query(F.data.startswith("dialog_send_"))
async def dialog_send_message(callback: CallbackQuery):
    """Отправка сообщения в диалог"""
    # TODO: Реализовать механизм отправки сообщений через состояния
    await callback.answer("🚧 Функция в разработке")


@dialogs_router.callback_query(F.data.startswith("dialog_toggle_ai_"))
async def dialog_toggle_ai(callback: CallbackQuery):
    """Переключение ИИ для конкретного диалога"""
    # TODO: Добавить поле ai_disabled в модель Conversation
    await callback.answer("🚧 Функция в разработке")


@dialogs_router.callback_query(F.data.startswith("dialog_delete_"))
async def dialog_delete(callback: CallbackQuery):
    """Удаление диалога"""
    try:
        conv_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            # Удаляем все сообщения диалога
            from sqlalchemy import delete
            await db.execute(delete(DBMessage).where(DBMessage.conversation_id == conv_id))

            # Удаляем сам диалог
            await db.execute(delete(Conversation).where(Conversation.id == conv_id))

            await db.commit()

        await callback.answer("✅ Диалог удален")
        await dialogs_list(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка удаления диалога: {e}")
        await callback.answer("❌ Ошибка удаления диалога")