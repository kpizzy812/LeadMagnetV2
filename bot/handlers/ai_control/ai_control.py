# bot/handlers/ai_control/ai_control.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import Session, Conversation, SessionStatus
from core.handlers.message_handler import message_handler
from loguru import logger
import asyncio

ai_control_router = Router()

# Глобальный флаг для отключения всей системы ИИ
GLOBAL_AI_ENABLED = True


@ai_control_router.callback_query(F.data == "ai_control_main")
async def ai_control_main(callback: CallbackQuery):
    """Главное меню управления ИИ"""

    try:
        # Получаем статистику
        async with get_db() as db:
            # Всего сессий с включенным ИИ
            enabled_sessions_result = await db.execute(
                select(func.count(Session.id))
                .where(Session.ai_enabled == True)
            )
            enabled_sessions = enabled_sessions_result.scalar() or 0

            # Всего активных диалогов
            active_dialogs_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.status == "active",
                    Conversation.ai_disabled == False
                )
            )
            active_dialogs = active_dialogs_result.scalar() or 0

            # Приостановленных диалогов
            paused_dialogs_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.auto_responses_paused == True)
            )
            paused_dialogs = paused_dialogs_result.scalar() or 0

        global_status = "🟢 Включен" if GLOBAL_AI_ENABLED else "🔴 Отключен"

        text = f"""🤖 <b>Управление системой ИИ</b>

🌐 <b>Глобальный статус:</b> {global_status}

📊 <b>Статистика:</b>
• Сессий с ИИ: {enabled_sessions}
• Активных диалогов: {active_dialogs}
• Приостановленных: {paused_dialogs}

⚙️ <b>Уровни управления:</b>
• 🌐 Глобально - вся система
• 🤖 По сессиям - конкретные аккаунты  
• 💬 По диалогам - отдельные беседы"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔴 Выключить всё" if GLOBAL_AI_ENABLED else "🟢 Включить всё",
                        callback_data="ai_toggle_global"
                    )
                ],
                [
                    InlineKeyboardButton(text="🤖 Управление сессиями", callback_data="ai_sessions_control"),
                    InlineKeyboardButton(text="💬 Управление диалогами", callback_data="ai_dialogs_control")
                ],
                [
                    InlineKeyboardButton(text="⏸️ Пауза всех диалогов", callback_data="ai_pause_all"),
                    InlineKeyboardButton(text="▶️ Возобновить всё", callback_data="ai_resume_all")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="ai_control_main"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка меню управления ИИ: {e}")
        await callback.answer("❌ Ошибка загрузки")


@ai_control_router.callback_query(F.data == "ai_toggle_global")
async def ai_toggle_global(callback: CallbackQuery):
    """Глобальное включение/отключение ИИ"""

    global GLOBAL_AI_ENABLED
    GLOBAL_AI_ENABLED = not GLOBAL_AI_ENABLED

    status = "включена" if GLOBAL_AI_ENABLED else "отключена"

    if not GLOBAL_AI_ENABLED:
        # Отключаем все сессии
        active_sessions = await message_handler.get_active_sessions()
        for session_name in active_sessions:
            await message_handler.remove_session(session_name)

        await callback.answer(f"🔴 Система ИИ {status}")
    else:
        # Включаем все активные сессии
        async with get_db() as db:
            result = await db.execute(
                select(Session).where(
                    Session.status == SessionStatus.ACTIVE,
                    Session.ai_enabled == True
                )
            )
            sessions = result.scalars().all()

            for session in sessions:
                await message_handler.add_session(session.session_name)

        await callback.answer(f"🟢 Система ИИ {status}")

    # Обновляем меню
    await ai_control_main(callback)


@ai_control_router.callback_query(F.data == "ai_pause_all")
async def ai_pause_all(callback: CallbackQuery):
    """Пауза всех диалогов"""

    try:
        async with get_db() as db:
            # Ставим на паузу все активные диалоги
            await db.execute(
                update(Conversation)
                .where(Conversation.status == "active")
                .values(auto_responses_paused=True)
            )
            await db.commit()

        await callback.answer("⏸️ Все диалоги приостановлены")
        await ai_control_main(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка приостановки диалогов: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_resume_all")
async def ai_resume_all(callback: CallbackQuery):
    """Возобновление всех диалогов"""

    try:
        async with get_db() as db:
            # Убираем паузу со всех диалогов
            await db.execute(
                update(Conversation)
                .values(
                    auto_responses_paused=False,
                    ai_disabled=False
                )
            )
            await db.commit()

        await callback.answer("▶️ Все диалоги возобновлены")
        await ai_control_main(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка возобновления диалогов: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_sessions_control")
async def ai_sessions_control(callback: CallbackQuery):
    """Управление ИИ по сессиям"""

    try:
        # Получаем статистику от message_handler
        from core.handlers.message_handler import message_handler
        session_stats = await message_handler.get_session_stats()

        if not session_stats:
            text = "🤖 <b>Управление ИИ по сессиям</b>\n\n📝 Сессий не найдено"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data="ai_control_main")
                ]]
            )
        else:
            text = "🤖 <b>Управление ИИ по сессиям</b>\n\n"

            # Группируем по статусам
            active_sessions = []
            paused_sessions = []
            inactive_sessions = []

            for session_name, stats in session_stats.items():
                status = stats.get("status", "unknown")
                persona = stats.get("persona_type", "не задана")

                if status == "active":
                    active_sessions.append((session_name, persona, stats))
                elif status == "paused":
                    paused_sessions.append((session_name, persona, stats))
                else:
                    inactive_sessions.append((session_name, persona, stats))

            # Показываем статистику
            text += f"✅ <b>Активных:</b> {len(active_sessions)}\n"
            text += f"⏸️ <b>Приостановленных:</b> {len(paused_sessions)}\n"
            text += f"❌ <b>Неактивных:</b> {len(inactive_sessions)}\n\n"

            # Показываем топ сессий
            all_sessions = active_sessions + paused_sessions + inactive_sessions

            keyboard_buttons = []

            for i, (session_name, persona, stats) in enumerate(all_sessions[:8]):  # Первые 8
                status = stats.get("status", "unknown")
                ai_enabled = stats.get("ai_enabled", False)

                status_emoji = {
                    "active": "🟢",
                    "paused": "⏸️",
                    "inactive": "🔴",
                    "disconnected": "⚠️"
                }.get(status, "❓")

                text += f"{status_emoji} <code>{session_name}</code> ({persona})\n"
                text += f"   💬 Диалогов: {stats.get('active_dialogs', 0)} | Сообщений 24ч: {stats.get('messages_24h', 0)}\n"

                # Кнопка управления
                if status == "active":
                    button_text = f"⏸️ Пауза {session_name}"
                    callback_data = f"ai_pause_session_{session_name}"
                elif status == "paused":
                    button_text = f"▶️ Запуск {session_name}"
                    callback_data = f"ai_resume_session_{session_name}"
                else:
                    button_text = f"🔄 Перезапуск {session_name}"
                    callback_data = f"ai_restart_session_{session_name}"

                keyboard_buttons.append([
                    InlineKeyboardButton(text=button_text, callback_data=callback_data)
                ])

            # Управляющие кнопки
            keyboard_buttons.extend([
                [
                    InlineKeyboardButton(text="⏸️ Пауза всех", callback_data="ai_pause_all_sessions"),
                    InlineKeyboardButton(text="▶️ Запуск всех", callback_data="ai_resume_all_sessions")
                ],
                [
                    InlineKeyboardButton(text="🧹 Очистить неактивные", callback_data="ai_cleanup_sessions"),
                    InlineKeyboardButton(text="📊 Детальная статистика", callback_data="ai_detailed_stats")
                ],
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="ai_sessions_control"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="ai_control_main")
                ]
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка управления сессиями: {e}")
        await callback.answer("❌ Ошибка загрузки")


@ai_control_router.callback_query(F.data.startswith("ai_pause_session_"))
async def ai_pause_session(callback: CallbackQuery):
    """Приостановка конкретной сессии"""

    try:
        session_name = callback.data.replace("ai_pause_session_", "")

        from core.handlers.message_handler import message_handler
        success = await message_handler.pause_session(session_name)

        if success:
            await callback.answer(f"⏸️ Сессия {session_name} приостановлена")
        else:
            await callback.answer(f"❌ Не удалось приостановить {session_name}")

        # Обновляем список
        await ai_sessions_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка приостановки сессии: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data.startswith("ai_resume_session_"))
async def ai_resume_session(callback: CallbackQuery):
    """Возобновление конкретной сессии"""

    try:
        session_name = callback.data.replace("ai_resume_session_", "")

        from core.handlers.message_handler import message_handler
        success = await message_handler.resume_session(session_name)

        if success:
            await callback.answer(f"▶️ Сессия {session_name} возобновлена")
        else:
            await callback.answer(f"❌ Не удалось возобновить {session_name}")

        # Обновляем список
        await ai_sessions_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка возобновления сессии: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data.startswith("ai_restart_session_"))
async def ai_restart_session(callback: CallbackQuery):
    """Перезапуск конкретной сессии"""

    try:
        session_name = callback.data.replace("ai_restart_session_", "")

        from core.handlers.message_handler import message_handler

        # Удаляем и добавляем заново
        await message_handler.remove_session(session_name)
        await asyncio.sleep(1)
        await message_handler.add_session(session_name)

        await callback.answer(f"🔄 Сессия {session_name} перезапущена")

        # Обновляем список
        await ai_sessions_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка перезапуска сессии: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_pause_all_sessions")
async def ai_pause_all_sessions(callback: CallbackQuery):
    """Приостановка всех сессий"""

    try:
        from core.handlers.message_handler import message_handler

        active_sessions = await message_handler.get_active_sessions()
        paused_count = 0

        for session_name in active_sessions:
            success = await message_handler.pause_session(session_name)
            if success:
                paused_count += 1

        await callback.answer(f"⏸️ Приостановлено {paused_count} сессий")
        await ai_sessions_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка приостановки всех сессий: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_resume_all_sessions")
async def ai_resume_all_sessions(callback: CallbackQuery):
    """Возобновление всех сессий"""

    try:
        from core.handlers.message_handler import message_handler

        session_stats = await message_handler.get_session_stats()
        resumed_count = 0

        for session_name, stats in session_stats.items():
            if stats.get("status") != "active":
                success = await message_handler.resume_session(session_name)
                if success:
                    resumed_count += 1

        await callback.answer(f"▶️ Возобновлено {resumed_count} сессий")
        await ai_sessions_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка возобновления всех сессий: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_cleanup_sessions")
async def ai_cleanup_sessions(callback: CallbackQuery):
    """Очистка неактивных сессий"""

    try:
        from core.handlers.message_handler import message_handler

        cleaned_count = await message_handler.cleanup_inactive_sessions()

        if cleaned_count > 0:
            await callback.answer(f"🧹 Очищено {cleaned_count} неактивных сессий")
        else:
            await callback.answer("✅ Все сессии активны")

        await ai_sessions_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка очистки сессий: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_detailed_stats")
async def ai_detailed_stats(callback: CallbackQuery):
    """Детальная статистика сессий"""

    try:
        from core.handlers.message_handler import message_handler

        # Получаем детальную статистику
        session_stats = await message_handler.get_session_stats()
        realtime_stats = message_handler.get_realtime_stats()

        text = f"""📊 <b>Детальная статистика сессий</b>

🔄 <b>Общая статистика:</b>
• Активных сессий: {realtime_stats.get('active_sessions', 0)}
• Приостановленных: {realtime_stats.get('paused_sessions', 0)}
• Очередь сообщений: {realtime_stats.get('queue_size', 0)}
• Задержки ответов: {realtime_stats.get('total_response_delays', 0)}

📈 <b>Топ сессий по активности:</b>"""

        # Сортируем по сообщениям за 24ч
        sorted_sessions = sorted(
            session_stats.items(),
            key=lambda x: x[1].get('messages_24h', 0),
            reverse=True
        )

        for session_name, stats in sorted_sessions[:5]:
            status_emoji = {
                "active": "🟢",
                "paused": "⏸️",
                "inactive": "🔴"
            }.get(stats.get("status"), "❓")

            text += f"\n{status_emoji} <code>{session_name}</code>"
            text += f"\n   📊 Сообщений 24ч: {stats.get('messages_24h', 0)}"
            text += f"\n   💬 Активных диалогов: {stats.get('active_dialogs', 0)}"
            text += f"\n   📈 Всего конверсий: {stats.get('total_conversions', 0)}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="ai_detailed_stats"),
                    InlineKeyboardButton(text="🔙 Назад", callback_data="ai_sessions_control")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка детальной статистики: {e}")
        await callback.answer("❌ Ошибка загрузки")

@ai_control_router.callback_query(F.data.startswith("ai_toggle_session_"))
async def ai_toggle_session(callback: CallbackQuery):
    """Переключение ИИ для конкретной сессии"""

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

            # Переключаем статус ИИ
            session.ai_enabled = not session.ai_enabled
            await db.commit()

            # Уведомляем обработчик сообщений
            if session.ai_enabled:
                await message_handler.add_session(session.session_name)
            else:
                await message_handler.remove_session(session.session_name)

            status = "включен" if session.ai_enabled else "отключен"
            await callback.answer(f"✅ ИИ для {session.session_name} {status}")

            # Обновляем список
            await ai_sessions_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка переключения ИИ сессии: {e}")
        await callback.answer("❌ Ошибка")


@ai_control_router.callback_query(F.data == "ai_dialogs_control")
async def ai_dialogs_control(callback: CallbackQuery):
    """Управление ИИ по диалогам"""

    try:
        async with get_db() as db:
            # Получаем диалоги требующие внимания
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(
                    Conversation.status == "active",
                    (Conversation.ai_disabled == True) | (Conversation.auto_responses_paused == True)
                )
                .order_by(Conversation.updated_at.desc())
                .limit(10)
            )
            problem_dialogs = result.scalars().all()

        text = "💬 <b>Управление ИИ по диалогам</b>\n\n"

        if not problem_dialogs:
            text += "✅ Все диалоги работают нормально"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Назад", callback_data="ai_control_main")
                ]]
            )
        else:
            text += f"⚠️ Найдено {len(problem_dialogs)} диалогов с проблемами:\n\n"

            keyboard_buttons = []
            for conv in problem_dialogs:
                status = "🔴 ИИ выкл" if conv.ai_disabled else "⏸️ Пауза"
                text += f"{status} @{conv.lead.username} ↔ {conv.session.session_name}\n"

                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"🔄 Восстановить {conv.lead.username}",
                        callback_data=f"ai_restore_dialog_{conv.id}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton(text="🔙 Назад", callback_data="ai_control_main")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка управления диалогами: {e}")
        await callback.answer("❌ Ошибка загрузки")


@ai_control_router.callback_query(F.data.startswith("ai_restore_dialog_"))
async def ai_restore_dialog(callback: CallbackQuery):
    """Восстановление ИИ для диалога"""

    try:
        conv_id = int(callback.data.split("_")[-1])

        async with get_db() as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conv_id)
                .values(
                    ai_disabled=False,
                    auto_responses_paused=False
                )
            )
            await db.commit()

        await callback.answer("✅ ИИ для диалога восстановлен")
        await ai_dialogs_control(callback)

    except Exception as e:
        logger.error(f"❌ Ошибка восстановления диалога: {e}")
        await callback.answer("❌ Ошибка")