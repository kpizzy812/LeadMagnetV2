# bot/handlers/dialogs.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select, func, update
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import Conversation, Lead, Session, Message as DBMessage
from loguru import logger

dialogs_router = Router()

class DialogStates(StatesGroup):
    """Состояния для диалогов"""
    waiting_message = State()

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

        # Добавляем кнопку фильтров
        keyboard_buttons.append([
            InlineKeyboardButton(text="🛡️ Фильтры", callback_data="dialogs_filters")
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
        ai_status = "🤖 Включен" if conversation.session.ai_enabled else "📴 Отключен"

        text = f"""💬 <b>Диалог с @{conversation.lead.username}</b>

👤 <b>Лид:</b> @{conversation.lead.username}
🤖 <b>Сессия:</b> {conversation.session.session_name}
🎭 <b>Персона:</b> {conversation.session.persona_type or 'не задана'}

📊 <b>Статус:</b> {conversation.status}
🎯 <b>Этап:</b> {conversation.current_stage}
🔗 <b>Реф ссылка:</b> {'✅ отправлена' if conversation.ref_link_sent else '❌ не отправлена'}
{ai_status}

📈 <b>Статистика:</b>
• Всего сообщений: {conversation.messages_count}
• От пользователя: {conversation.user_messages_count}
• От ассистента: {conversation.assistant_messages_count}

📅 <b>Создан:</b> {conversation.created_at.strftime('%d.%m.%Y %H:%M')}
🕐 <b>Обновлен:</b> {conversation.updated_at.strftime('%d.%m.%Y %H:%M')}"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 История",
                        callback_data=f"dialog_history_{conv_id}"
                    ),
                    InlineKeyboardButton(
                        text="✏️ Написать",
                        callback_data=f"dialog_send_{conv_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🤖 ИИ вкл/выкл",
                        callback_data=f"dialog_toggle_ai_{conv_id}"
                    ),
                    InlineKeyboardButton(
                        text="📈 Аналитика",
                        callback_data=f"dialog_analytics_{conv_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🗑️ Удалить",
                        callback_data=f"dialog_delete_{conv_id}"
                    ),
                    InlineKeyboardButton(text="🔙 К списку", callback_data="dialogs_list")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка просмотра диалога: {e}")
        await callback.answer("❌ Ошибка загрузки диалога")


@dialogs_router.callback_query(F.data.startswith("dialog_history_"))
async def dialog_history(callback: CallbackQuery):
    """Просмотр истории переписки"""

    try:
        conv_id = int(callback.data.split("_")[-1])
        page = 0  # Можно добавить пагинацию позже

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

        text = f"💬 <b>История: @{conversation.lead.username} ↔ {conversation.session.session_name}</b>\n\n"

        # Показываем последние 15 сообщений
        messages = conversation.messages[-15:] if conversation.messages else []

        if not messages:
            text += "📝 Сообщений пока нет"
        else:
            for msg in messages:
                role_emoji = "👤" if msg.role == "user" else "🤖"
                time_str = msg.created_at.strftime('%d.%m %H:%M')

                # Обрезаем длинные сообщения
                content = msg.content
                if len(content) > 100:
                    content = content[:100] + "..."

                text += f"{role_emoji} <b>[{time_str}]</b>\n{content}\n\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Написать сообщение",
                        callback_data=f"dialog_send_{conv_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить",
                        callback_data=f"dialog_history_{conv_id}"
                    ),
                    InlineKeyboardButton(
                        text="🔙 К диалогу",
                        callback_data=f"dialog_view_{conv_id}"
                    )
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка просмотра истории: {e}")
        await callback.answer("❌ Ошибка загрузки истории")


@dialogs_router.callback_query(F.data.startswith("dialog_send_"))
async def dialog_send_message(callback: CallbackQuery, state: FSMContext):
    """Отправка сообщения в диалог"""

    try:
        conv_id = int(callback.data.split("_")[-1])

        # Сохраняем ID диалога в состояние
        await state.update_data(conversation_id=conv_id)

        # Получаем информацию о диалоге
        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(Conversation.id == conv_id)
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                await callback.answer("❌ Диалог не найден")
                return

        text = f"""✏️ <b>Отправка сообщения</b>

👤 <b>Лид:</b> @{conversation.lead.username}
🤖 <b>Сессия:</b> {conversation.session.session_name}
🎭 <b>Персона:</b> {conversation.session.persona_type or 'не задана'}

📝 Введите текст сообщения для отправки:

⚠️ <b>Внимание:</b> Сообщение будет отправлено от имени сессии
💡 Для отмены напишите /cancel"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"dialog_view_{conv_id}")
            ]]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(DialogStates.waiting_message)

    except Exception as e:
        logger.error(f"❌ Ошибка подготовки отправки сообщения: {e}")
        await callback.answer("❌ Ошибка")


@dialogs_router.message(DialogStates.waiting_message)
async def dialog_message_received(message: Message, state: FSMContext):
    """Получение текста для отправки в диалог"""

    try:
        data = await state.get_data()
        conv_id = data.get("conversation_id")
        message_text = message.text

        if not message_text or len(message_text.strip()) < 1:
            await message.answer("❌ Сообщение не может быть пустым. Попробуйте еще раз:")
            return

        # Получаем диалог
        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(Conversation.id == conv_id)
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                await message.answer("❌ Диалог не найден")
                await state.clear()
                return

        # Отправляем сообщение через Telegram
        from core.integrations.telegram_client import telegram_session_manager

        success = await telegram_session_manager.send_message(
            session_name=conversation.session.session_name,
            username=conversation.lead.username,
            message=message_text
        )

        if success:
            # Сохраняем сообщение в БД
            from storage.models.base import Message as DBMessage, MessageRole

            async with get_db() as db:
                db_message = DBMessage(
                    conversation_id=conversation.id,
                    lead_id=conversation.lead_id,
                    session_id=conversation.session_id,
                    role=MessageRole.ASSISTANT,
                    content=message_text,
                    funnel_stage=conversation.current_stage,
                    processed=True
                )
                db.add(db_message)

                # Обновляем статистику
                conversation.messages_count += 1
                conversation.assistant_messages_count += 1
                conversation.last_assistant_message_at = datetime.utcnow()

                await db.commit()

            await message.answer(
                f"✅ Сообщение отправлено!\n\n"
                f"👤 Получатель: @{conversation.lead.username}\n"
                f"🤖 От имени: {conversation.session.session_name}"
            )

            logger.success(
                f"📤 Ручное сообщение отправлено: {conversation.session.session_name} → {conversation.lead.username}")

        else:
            await message.answer("❌ Не удалось отправить сообщение")

        await state.clear()

    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения в диалог: {e}")
        await message.answer("❌ Ошибка отправки сообщения")
        await state.clear()

@dialogs_router.message(lambda message: message.text == "/cancel")
async def cancel_dialog_action(message: Message, state: FSMContext):
    """Отмена действия в диалоге"""

    await state.clear()
    await message.answer("❌ Действие отменено")

@dialogs_router.callback_query(F.data.startswith("dialog_toggle_ai_"))
async def dialog_toggle_ai(callback: CallbackQuery):
    """Переключение ИИ для конкретного диалога"""

    try:
        conv_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            # Получаем диалог
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.session))
                .where(Conversation.id == conv_id)
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                await callback.answer("❌ Диалог не найден")
                return

            # Переключаем ИИ для всей сессии
            session = conversation.session
            session.ai_enabled = not session.ai_enabled
            await db.commit()

            # Уведомляем обработчик сообщений
            from core.handlers.message_handler import message_handler
            if session.ai_enabled:
                await message_handler.add_session(session.session_name)
            else:
                await message_handler.remove_session(session.session_name)

            status = "включен" if session.ai_enabled else "отключен"
            await callback.answer(f"✅ ИИ для сессии {session.session_name} {status}")

            # Обновляем информацию о диалоге
            await dialog_view(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка переключения ИИ для диалога: {e}")
        await callback.answer("❌ Ошибка переключения ИИ")


@dialogs_router.callback_query(F.data.startswith("approve_conversation_"))
async def approve_conversation(callback: CallbackQuery):
    """Одобрение диалога"""

    try:
        conv_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conv_id)
                .values(
                    is_whitelisted=True,
                    requires_approval=False
                )
            )
            await db.commit()

        await callback.answer("✅ Диалог одобрен")
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>ОДОБРЕНО</b>"
        )

    except Exception as e:
        logger.error(f"❌ Ошибка одобрения диалога: {e}")
        await callback.answer("❌ Ошибка")


@dialogs_router.callback_query(F.data.startswith("reject_conversation_"))
async def reject_conversation(callback: CallbackQuery):
    """Отклонение диалога"""

    try:
        conv_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conv_id)
                .values(
                    is_blacklisted=True,
                    requires_approval=False
                )
            )
            await db.commit()

        await callback.answer("🚫 Диалог отклонен")
        await callback.message.edit_text(
            callback.message.text + "\n\n🚫 <b>ОТКЛОНЕНО</b>"
        )

    except Exception as e:
        logger.error(f"❌ Ошибка отклонения диалога: {e}")
        await callback.answer("❌ Ошибка")


# 5. Добавить раздел управления фильтрами в бот:

@dialogs_router.callback_query(F.data == "dialogs_filters")
async def dialogs_filters_main(callback: CallbackQuery):
    """Управление фильтрами диалогов"""

    try:
        async with get_db() as db:
            # Статистика по фильтрам
            pending_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.requires_approval == True)
            )
            pending = pending_result.scalar() or 0

            whitelisted_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.is_whitelisted == True)
            )
            whitelisted = whitelisted_result.scalar() or 0

            blacklisted_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.is_blacklisted == True)
            )
            blacklisted = blacklisted_result.scalar() or 0

        text = f"""🛡️ <b>Фильтры диалогов</b>

📊 <b>Статистика:</b>
• Ожидают одобрения: {pending}
• В белом списке: {whitelisted}
• В черном списке: {blacklisted}

⚙️ <b>Настройки:</b>
Система автоматически фильтрует диалоги по ключевым словам и поведению пользователей."""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⏳ Ожидают одобрения", callback_data="dialogs_pending"),
                    InlineKeyboardButton(text="✅ Белый список", callback_data="dialogs_whitelist")
                ],
                [
                    InlineKeyboardButton(text="🚫 Черный список", callback_data="dialogs_blacklist"),
                    InlineKeyboardButton(text="⚙️ Настройки", callback_data="dialogs_filter_settings")
                ],
                [
                    InlineKeyboardButton(text="🔙 К диалогам", callback_data="dialogs_list")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню фильтров: {e}")
        await callback.answer("❌ Ошибка загрузки")


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


@dialogs_router.callback_query(F.data == "dialogs_pending")
async def dialogs_pending(callback: CallbackQuery):
    """Диалоги ожидающие одобрения"""

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(Conversation.requires_approval == True)
                .order_by(Conversation.created_at.desc())
                .limit(10)
            )
            conversations = result.scalars().all()

        if not conversations:
            text = "⏳ <b>Ожидающие одобрения</b>\n\n📝 Нет диалогов требующих одобрения"
        else:
            text = f"⏳ <b>Ожидающие одобрения ({len(conversations)})</b>\n\n"

            for conv in conversations:
                time_ago = datetime.now() - conv.created_at
                hours_ago = int(time_ago.total_seconds() / 3600)

                text += f"👤 @{conv.lead.username}\n"
                text += f"🤖 {conv.session.session_name}\n"
                text += f"⏰ {hours_ago}ч назад\n\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="dialogs_pending"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dialogs_filters")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка списка ожидающих: {e}")
        await callback.answer("❌ Ошибка загрузки")


@dialogs_router.callback_query(F.data == "dialogs_whitelist")
async def dialogs_whitelist(callback: CallbackQuery):
    """Диалоги в белом списке"""

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(Conversation.is_whitelisted == True)
                .order_by(Conversation.updated_at.desc())
                .limit(10)
            )
            conversations = result.scalars().all()

        if not conversations:
            text = "✅ <b>Белый список</b>\n\n📝 Нет диалогов в белом списке"
        else:
            text = f"✅ <b>Белый список ({len(conversations)})</b>\n\n"

            for conv in conversations:
                status_emoji = "🟢" if conv.status == "active" else "🔴"
                text += f"{status_emoji} @{conv.lead.username} ↔ {conv.session.session_name}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="dialogs_whitelist"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dialogs_filters")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка белого списка: {e}")
        await callback.answer("❌ Ошибка загрузки")


@dialogs_router.callback_query(F.data == "dialogs_blacklist")
async def dialogs_blacklist(callback: CallbackQuery):
    """Диалоги в черном списке"""

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(Conversation.is_blacklisted == True)
                .order_by(Conversation.updated_at.desc())
                .limit(10)
            )
            conversations = result.scalars().all()

        if not conversations:
            text = "🚫 <b>Черный список</b>\n\n📝 Нет диалогов в черном списке"
        else:
            text = f"🚫 <b>Черный список ({len(conversations)})</b>\n\n"

            for conv in conversations:
                text += f"🚫 @{conv.lead.username} ↔ {conv.session.session_name}\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="dialogs_blacklist"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dialogs_filters")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка черного списка: {e}")
        await callback.answer("❌ Ошибка загрузки")


@dialogs_router.callback_query(F.data == "dialogs_filter_settings")
async def dialogs_filter_settings(callback: CallbackQuery):
    """Настройки фильтров"""

    text = """⚙️ <b>Настройки фильтров</b>

🔍 <b>Автоматическая фильтрация:</b>
• Белый список - ключевые слова: проект, инвест, заработок
• Черный список - ключевые слова: спам, реклама, скидка
• Новые диалоги требуют одобрения

📝 <b>Ручное управление:</b>
• Одобрить диалог - добавить в белый список
• Отклонить диалог - добавить в черный список
• Изменить статус в разделе диалогов

💡 <b>Рекомендации:</b>
• Регулярно проверяйте ожидающие одобрения
• Анализируйте черный список на предмет ошибок
• Добавляйте проверенных лидов в белый список"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="dialogs_filters")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)