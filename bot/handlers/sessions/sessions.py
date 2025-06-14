# bot/handlers/sessions/sessions.py - ОБНОВЛЕННЫЙ ДЛЯ РЕТРОСПЕКТИВНОЙ СИСТЕМЫ

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models import Session, SessionStatus, PersonaType, Conversation, ConversationStatus
from core.scanning.retrospective_scanner import retrospective_scanner
from core.handlers.message_handler import message_handler
from loguru import logger

sessions_router = Router()


@sessions_router.callback_query(F.data == "sessions_list")
async def sessions_list(callback: CallbackQuery):
    """Список всех сессий с ретроспективной статистикой"""

    try:
        async with get_db() as db:
            # Получаем сессии с статистикой диалогов
            result = await db.execute(
                select(Session).order_by(Session.created_at.desc()).limit(20)
            )
            sessions = result.scalars().all()

        if not sessions:
            await callback.message.edit_text(
                "📝 Сессии не найдены",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                    ]]
                )
            )
            return

        # Получаем статистику сканера
        scanner_stats = retrospective_scanner.get_stats()

        text = f"""👥 <b>Список сессий</b>

🔍 <b>Ретроспективное сканирование:</b>
• Статус: {'🟢 Активно' if scanner_stats.get('is_running') else '🔴 Неактивно'}
• Интервал: {scanner_stats.get('scan_interval', 0)} сек
• Новых сообщений: {scanner_stats.get('total_new_messages', 0)}

📋 <b>Сессии:</b>

"""

        keyboard_buttons = []

        for session in sessions:
            # Статистика диалогов для сессии
            async with get_db() as db:
                dialogs_result = await db.execute(
                    select(func.count(Conversation.id)).where(
                        Conversation.session_name == session.session_name
                    )
                )
                total_dialogs = dialogs_result.scalar() or 0

                # Ожидающие одобрения
                pending_result = await db.execute(
                    select(func.count(Conversation.id)).where(
                        Conversation.session_name == session.session_name,
                        Conversation.requires_approval == True,
                        Conversation.admin_approved == False
                    )
                )
                pending_approvals = pending_result.scalar() or 0

            status_emoji = {
                SessionStatus.ACTIVE: "🟢",
                SessionStatus.INACTIVE: "🟡",
                SessionStatus.ERROR: "⚠️"
            }.get(session.status, "❓")

            ai_status = "🤖" if session.ai_enabled else "📴"
            scan_status = "🔍" if session.ai_enabled and session.status == SessionStatus.ACTIVE else "⏸️"

            text += f"{status_emoji} {ai_status} {scan_status} <code>{session.session_name}</code>\n"
            text += f"   • Персона: {session.persona_type or 'не задана'}\n"
            text += f"   • Диалогов: {total_dialogs} (ожидает: {pending_approvals})\n"
            text += f"   • Конверсий: {session.total_conversions}\n\n"

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"⚙️ {session.session_name}",
                    callback_data=f"session_manage_{session.id}"
                )
            ])

        # Кнопки управления
        keyboard_buttons.extend([
            [
                InlineKeyboardButton(text="🔍 Принудительное сканирование", callback_data="force_scan_now"),
                InlineKeyboardButton(text="✅ Одобрения", callback_data="pending_approvals")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="sessions_list")
            ]
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка получения списка сессий: {e}")
        await callback.answer("❌ Ошибка загрузки сессий")


@sessions_router.callback_query(F.data == "force_scan_now")
async def force_scan_now(callback: CallbackQuery):
    """Принудительное сканирование всех сессий"""
    try:
        await callback.answer("🔍 Запускаем принудительное сканирование...")

        result = await message_handler.force_scan_now()

        if result.get("success"):
            text = f"""✅ <b>Принудительное сканирование завершено!</b>

🕐 <b>Время запуска:</b> {result.get('timestamp', 'неизвестно')}

Результаты можно увидеть в обновленном списке сессий."""
        else:
            text = f"""❌ <b>Ошибка принудительного сканирования</b>

{result.get('error', 'Неизвестная ошибка')}"""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Список сессий", callback_data="sessions_list"),
                InlineKeyboardButton(text="🔄 Повторить", callback_data="force_scan_now")
            ]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка принудительного сканирования: {e}")
        await callback.answer("Ошибка запуска сканирования", show_alert=True)


@sessions_router.callback_query(F.data == "pending_approvals")
async def pending_approvals(callback: CallbackQuery):
    """Диалоги ожидающие одобрения админа"""
    try:
        pending = await message_handler.get_pending_approvals()

        if not pending:
            text = """✅ <b>Нет диалогов ожидающих одобрения</b>

Все новые диалоги одобрены или система настроена на автоматическое одобрение."""

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="sessions_list")]
            ])
        else:
            text = f"🔔 <b>Диалоги ожидающие одобрения ({len(pending)})</b>\n\n"

            keyboard_buttons = []

            for conv in pending[:10]:  # Показываем максимум 10
                last_msg_time = ""
                if conv['last_message_time']:
                    last_msg_time = conv['last_message_time'].strftime('%d.%m %H:%M')

                text += f"👤 <b>@{conv['lead_username']}</b>\n"
                text += f"🤖 Сессия: {conv['session_name']}\n"
                text += f"💬 Сообщений: {conv['total_messages']}\n"
                text += f"🕐 Последнее: {last_msg_time}\n"
                if conv['last_message']:
                    text += f"📝 Текст: {conv['last_message'][:100]}...\n"
                text += "\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"✅ Одобрить @{conv['lead_username']}",
                        callback_data=f"approve_conv_{conv['conversation_id']}"
                    ),
                    InlineKeyboardButton(
                        text="❌",
                        callback_data=f"reject_conv_{conv['conversation_id']}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton(text="🔙 Назад", callback_data="sessions_list")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки одобрений: {e}")
        await callback.answer("Ошибка загрузки одобрений", show_alert=True)


@sessions_router.callback_query(F.data.startswith("approve_conv_"))
async def approve_conversation(callback: CallbackQuery):
    """Одобрение конкретного диалога"""
    try:
        conv_id = int(callback.data.split("_")[-1])
        admin_id = callback.from_user.id

        success = await message_handler.approve_conversation(
            conversation_id=conv_id,
            admin_id=admin_id,
            comment="Одобрено через Telegram бота"
        )

        if success:
            await callback.answer("✅ Диалог одобрен!", show_alert=True)
            await pending_approvals(callback)  # Обновляем список
        else:
            await callback.answer("❌ Ошибка одобрения", show_alert=True)

    except Exception as e:
        logger.error(f"❌ Ошибка одобрения диалога: {e}")
        await callback.answer("Ошибка одобрения", show_alert=True)


@sessions_router.callback_query(F.data.startswith("reject_conv_"))
async def reject_conversation(callback: CallbackQuery):
    """Отклонение конкретного диалога"""
    try:
        conv_id = int(callback.data.split("_")[-1])
        admin_id = callback.from_user.id

        success = await message_handler.reject_conversation(
            conversation_id=conv_id,
            admin_id=admin_id,
            comment="Отклонено через Telegram бота"
        )

        if success:
            await callback.answer("🚫 Диалог отклонен!", show_alert=True)
            await pending_approvals(callback)  # Обновляем список
        else:
            await callback.answer("❌ Ошибка отклонения", show_alert=True)

    except Exception as e:
        logger.error(f"❌ Ошибка отклонения диалога: {e}")
        await callback.answer("Ошибка отклонения", show_alert=True)


@sessions_router.callback_query(F.data.startswith("session_manage_"))
async def session_manage(callback: CallbackQuery):
    """Управление конкретной сессией"""

    try:
        session_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

        if not session:
            await callback.answer("❌ Сессия не найдена")
            return

        # Получаем статистику диалогов
        session_status = await message_handler.get_session_status(session.session_name)

        status_emoji = {
            SessionStatus.ACTIVE: "🟢 Активна",
            SessionStatus.INACTIVE: "🟡 Неактивна",
            SessionStatus.ERROR: "⚠️ Ошибка"
        }.get(session.status, "❓ Неизвестно")

        ai_status = "🤖 Включен" if session.ai_enabled else "📴 Отключен"
        scanning_status = "🔍 Сканируется" if session_status.get('scanning_enabled') else "⏸️ Приостановлено"

        text = f"""⚙️ <b>Управление сессией</b>

📱 <b>Сессия:</b> <code>{session.session_name}</code>
🔐 <b>Telegram ID:</b> <code>{session.telegram_id or 'неизвестен'}</code>
👤 <b>Username:</b> @{session.username or 'неизвестен'}
🎭 <b>Персона:</b> {session.persona_type or 'не задана'}

📊 <b>Статус:</b> {status_emoji}
🤖 <b>ИИ:</b> {ai_status}
🔍 <b>Сканирование:</b> {scanning_status}

📈 <b>Статистика:</b>
• Диалогов: {session_status.get('total_conversations', 0)}
• Ожидают одобрения: {session_status.get('pending_approvals', 0)}
• Конверсий: {session.total_conversions}

🔗 <b>Реф ссылка:</b> {session.project_ref_link or 'не задана'}"""

        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    text="⏸️ Остановить сканирование" if session.ai_enabled else "▶️ Запустить сканирование",
                    callback_data=f"session_toggle_scanning_{session.id}"
                ),
                InlineKeyboardButton(
                    text="🎭 Персона",
                    callback_data=f"session_persona_{session.id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Диалоги",
                    callback_data=f"session_dialogs_{session.id}"
                ),
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data=f"session_stats_{session.id}"
                )
            ]
        ]

        if session_status.get('pending_approvals', 0) > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"✅ Одобрения ({session_status['pending_approvals']})",
                    callback_data=f"session_approvals_{session.id}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 К списку", callback_data="sessions_list")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка управления сессией: {e}")
        await callback.answer("❌ Ошибка загрузки сессии")


@sessions_router.callback_query(F.data.startswith("session_toggle_scanning_"))
async def session_toggle_scanning(callback: CallbackQuery):
    """Переключение сканирования для сессии"""

    try:
        session_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                await callback.answer("❌ Сессия не найдена")
                return

            if session.ai_enabled:
                success = await message_handler.pause_session_scanning(session.session_name)
                status = "приостановлено" if success else "ошибка приостановки"
            else:
                success = await message_handler.resume_session_scanning(session.session_name)
                status = "запущено" if success else "ошибка запуска"

            if success:
                await callback.answer(f"✅ Сканирование {status}")
                await session_manage(callback)  # Обновляем информацию
            else:
                await callback.answer("❌ Ошибка переключения")

    except Exception as e:
        logger.error(f"❌ Ошибка переключения сканирования: {e}")
        await callback.answer("❌ Ошибка переключения")


@sessions_router.callback_query(F.data.startswith("session_persona_"))
async def session_persona_menu(callback: CallbackQuery):
    """Меню выбора персоны для сессии"""

    try:
        session_id = int(callback.data.split("_")[-1])

        text = "🎭 <b>Выберите персону для сессии:</b>\n\n"
        text += "👨 <b>Базовые персоны:</b>\n"
        text += "• <code>basic_man</code> - Простой парень\n"
        text += "• <code>basic_woman</code> - Простая девушка\n\n"
        text += "💼 <b>Продвинутые:</b>\n"
        text += "• <code>hyip_man</code> - HYIP эксперт\n"
        text += "• <code>investor_man</code> - Инвестор\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👨 Простой парень",
                        callback_data=f"session_set_persona_{session_id}_basic_man"
                    ),
                    InlineKeyboardButton(
                        text="👩 Простая девушка",
                        callback_data=f"session_set_persona_{session_id}_basic_woman"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="💼 HYIP мужчина",
                        callback_data=f"session_set_persona_{session_id}_hyip_man"
                    ),
                    InlineKeyboardButton(
                        text="📈 Инвестор",
                        callback_data=f"session_set_persona_{session_id}_investor_man"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад",
                        callback_data=f"session_manage_{session_id}"
                    )
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню персон: {e}")
        await callback.answer("❌ Ошибка загрузки меню")


@sessions_router.callback_query(F.data.startswith("session_set_persona_"))
async def session_set_persona(callback: CallbackQuery):
    """Установка персоны для сессии"""

    try:
        parts = callback.data.split("_")
        session_id = int(parts[3])
        persona_type = "_".join(parts[4:])  # basic_man, hyip_man и т.д.

        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                await callback.answer("❌ Сессия не найдена")
                return

            # Проверяем валидность персоны
            valid_personas = [p.value for p in PersonaType]
            if persona_type not in valid_personas:
                await callback.answer("❌ Неверная персона")
                return

            # Устанавливаем персону
            session.persona_type = persona_type
            await db.commit()

            persona_names = {
                PersonaType.BASIC_MAN.value: "Простой парень",
                PersonaType.BASIC_WOMAN.value: "Простая девушка",
                PersonaType.HYIP_MAN.value: "HYIP мужчина",
                PersonaType.INVESTOR_MAN.value: "Инвестор"
            }

            persona_name = persona_names.get(persona_type, persona_type)
            await callback.answer(f"✅ Установлена персона: {persona_name}")

            # Возвращаемся к управлению сессией
            await session_manage(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка установки персоны: {e}")
        await callback.answer("❌ Ошибка установки персоны")


@sessions_router.callback_query(F.data.startswith("session_dialogs_"))
async def session_dialogs(callback: CallbackQuery):
    """Диалоги конкретной сессии"""

    try:
        session_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            # Получаем сессию
            session_result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = session_result.scalar_one_or_none()

            if not session:
                await callback.answer("❌ Сессия не найдена")
                return

            # Получаем диалоги сессии
            result = await db.execute(
                select(Conversation)
                .where(Conversation.session_name == session.session_name)
                .order_by(Conversation.updated_at.desc())
                .limit(10)
            )
            conversations = result.scalars().all()

        if not conversations:
            text = f"💬 <b>Диалоги сессии {session.session_name}</b>\n\n"
            text += "📝 Диалогов пока нет"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 Назад",
                        callback_data=f"session_manage_{session_id}"
                    )
                ]]
            )
        else:
            text = f"💬 <b>Диалоги сессии {session.session_name}</b>\n\n"

            keyboard_buttons = []

            for conv in conversations:
                status_emoji = {
                    ConversationStatus.ACTIVE.value: "🟢",
                    ConversationStatus.PENDING_APPROVAL.value: "🔔",
                    ConversationStatus.APPROVED.value: "✅",
                    ConversationStatus.BLOCKED.value: "🔴"
                }.get(conv.status, "❓")

                ref_emoji = "🔗" if conv.ref_link_sent else "📝"
                approval_emoji = "⏳" if conv.requires_approval and not conv.admin_approved else ""

                text += f"{status_emoji} {ref_emoji} {approval_emoji} @{conv.lead_username}\n"
                text += f"   • Этап: {conv.current_stage}\n"
                text += f"   • Сообщений: {conv.total_messages_received}\n\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"👤 {conv.lead_username}",
                        callback_data=f"dialog_view_{conv.id}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data=f"session_manage_{session_id}"
                )
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки диалогов сессии: {e}")
        await callback.answer("❌ Ошибка загрузки диалогов")