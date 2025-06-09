# bot/handlers/broadcasts/broadcast.py

import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.base import Session, Conversation, Lead
from core.integrations.telegram_client import telegram_session_manager
from loguru import logger

broadcasts_router = Router()


class BroadcastStates(StatesGroup):
    """Состояния для рассылки"""
    waiting_message = State()
    waiting_confirmation = State()


@broadcasts_router.callback_query(F.data == "broadcast_main")
async def broadcast_main(callback: CallbackQuery):
    """Главное меню рассылок"""

    text = """📢 <b>Система рассылок</b>

Выберите тип рассылки:

🎯 <b>По всем лидам</b> - отправка всем лидам во всех сессиях
👥 <b>По сессии</b> - рассылка через конкретную сессию
🔗 <b>По статусу</b> - лидам с/без реф ссылки
🎭 <b>По персоне</b> - лидам определенных персон

⚠️ <b>Внимание:</b> Рассылки выполняются с задержками для безопасности"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 Всем лидам", callback_data="broadcast_all"),
                InlineKeyboardButton(text="👥 По сессии", callback_data="broadcast_session")
            ],
            [
                InlineKeyboardButton(text="🔗 По статусу", callback_data="broadcast_status"),
                InlineKeyboardButton(text="🎭 По персоне", callback_data="broadcast_persona")
            ],
            [
                InlineKeyboardButton(text="📊 История", callback_data="broadcast_history"),
                InlineKeyboardButton(text="🔙 Назад", callback_data="dashboard_refresh")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@broadcasts_router.callback_query(F.data == "broadcast_session")
async def broadcast_session_list(callback: CallbackQuery):
    """Выбор сессии для рассылки"""

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Session)
                .where(Session.status == 'active')
                .order_by(Session.session_name)
            )
            sessions = result.scalars().all()

        if not sessions:
            await callback.answer("❌ Нет активных сессий")
            return

        text = "👥 <b>Выберите сессию для рассылки:</b>\n\n"

        keyboard_buttons = []

        for session in sessions:
            text += f"🤖 <code>{session.session_name}</code>\n"
            text += f"   • Персона: {session.persona_type or 'не задана'}\n"
            text += f"   • Диалогов: {session.total_conversations}\n\n"

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📤 {session.session_name}",
                    callback_data=f"broadcast_session_select_{session.id}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_main")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки сессий для рассылки: {e}")
        await callback.answer("❌ Ошибка загрузки сессий")


@broadcasts_router.callback_query(F.data.startswith("broadcast_session_select_"))
async def broadcast_session_select(callback: CallbackQuery):
    """Настройка рассылки для выбранной сессии"""

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

            # Статистика по диалогам сессии
            total_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.session_id == session_id)
            )
            total_dialogs = total_result.scalar() or 0

            with_ref_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.session_id == session_id,
                    Conversation.ref_link_sent == True
                )
            )
            with_ref = with_ref_result.scalar() or 0

            without_ref = total_dialogs - with_ref

        text = f"""📤 <b>Рассылка через {session.session_name}</b>

🎭 <b>Персона:</b> {session.persona_type or 'не задана'}

📊 <b>Целевая аудитория:</b>
• Всего диалогов: {total_dialogs}
• С реф ссылкой: {with_ref}
• Без реф ссылки: {without_ref}

Выберите целевую группу:"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🎯 Всем ({total_dialogs})",
                        callback_data=f"broadcast_prepare_{session_id}_all"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"🔗 С реф ссылкой ({with_ref})",
                        callback_data=f"broadcast_prepare_{session_id}_with_ref"
                    ),
                    InlineKeyboardButton(
                        text=f"📝 Без реф ссылки ({without_ref})",
                        callback_data=f"broadcast_prepare_{session_id}_without_ref"
                    )
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_session")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка выбора сессии для рассылки: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@broadcasts_router.callback_query(F.data.startswith("broadcast_prepare_"))
async def broadcast_prepare(callback: CallbackQuery, state: FSMContext):
    """Подготовка к рассылке - запрос текста сообщения"""

    # Парсим параметры
    parts = callback.data.split("_")
    session_id = int(parts[2])
    target_type = parts[3]

    # Сохраняем параметры в состояние
    await state.update_data(
        session_id=session_id,
        target_type=target_type
    )

    text = """✏️ <b>Введите текст сообщения для рассылки:</b>

📝 Напишите сообщение, которое будет отправлено всем выбранным лидам.

⚠️ <b>Важно:</b>
• Сообщение будет отправлено от имени выбранной сессии
• Между отправками будут паузы 3-5 секунд
• Можно отменить рассылку командой /cancel

Введите ваш текст:"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_main")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(BroadcastStates.waiting_message)


@broadcasts_router.message(BroadcastStates.waiting_message)
async def broadcast_message_received(message: Message, state: FSMContext):
    """Получение текста сообщения для рассылки"""

    # Получаем данные из состояния
    data = await state.get_data()
    session_id = data["session_id"]
    target_type = data["target_type"]
    message_text = message.text

    if not message_text or len(message_text.strip()) < 1:
        await message.answer("❌ Сообщение не может быть пустым. Попробуйте еще раз:")
        return

    # Сохраняем текст сообщения
    await state.update_data(message_text=message_text)

    # Получаем информацию о рассылке
    async with get_db() as db:
        session_result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = session_result.scalar_one()

        # Подсчитываем получателей
        query = select(func.count(Conversation.id)).where(Conversation.session_id == session_id)

        if target_type == "with_ref":
            query = query.where(Conversation.ref_link_sent == True)
        elif target_type == "without_ref":
            query = query.where(Conversation.ref_link_sent == False)

        count_result = await db.execute(query)
        recipients_count = count_result.scalar() or 0

    # Показываем предпросмотр
    preview_text = f"""📋 <b>Предпросмотр рассылки</b>

📤 <b>Сессия:</b> {session.session_name}
🎯 <b>Получателей:</b> {recipients_count}
📝 <b>Фильтр:</b> {get_filter_name(target_type)}

💬 <b>Текст сообщения:</b>
<pre>{message_text}</pre>

⚠️ <b>Внимание:</b> После подтверждения рассылка начнется немедленно!"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_main")
            ]
        ]
    )

    await message.answer(preview_text, reply_markup=keyboard)
    await state.set_state(BroadcastStates.waiting_confirmation)


@broadcasts_router.callback_query(F.data == "broadcast_confirm", BroadcastStates.waiting_confirmation)
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и запуск рассылки"""

    # Получаем данные
    data = await state.get_data()
    session_id = data["session_id"]
    target_type = data["target_type"]
    message_text = data["message_text"]

    await callback.message.edit_text("🚀 <b>Рассылка запущена...</b>\n\nПодготавливаем список получателей...")

    try:
        # Получаем получателей
        recipients = await get_broadcast_recipients(session_id, target_type)

        if not recipients:
            await callback.message.edit_text("❌ <b>Нет получателей для рассылки</b>")
            await state.clear()
            return

        # Запускаем рассылку в фоне
        asyncio.create_task(
            execute_broadcast(
                callback.message,
                session_id,
                recipients,
                message_text
            )
        )

        await state.clear()

    except Exception as e:
        logger.error(f"❌ Ошибка запуска рассылки: {e}")
        await callback.message.edit_text("❌ <b>Ошибка запуска рассылки</b>\n\nПроверьте логи для подробностей.")
        await state.clear()


async def get_broadcast_recipients(session_id: int, target_type: str) -> list:
    """Получение списка получателей для рассылки"""

    try:
        async with get_db() as db:
            query = (
                select(Conversation)
                .options(selectinload(Conversation.lead))
                .options(selectinload(Conversation.session))
                .where(
                    Conversation.session_id == session_id,
                    Conversation.status == 'active'
                )
            )

            if target_type == "with_ref":
                query = query.where(Conversation.ref_link_sent == True)
            elif target_type == "without_ref":
                query = query.where(Conversation.ref_link_sent == False)

            result = await db.execute(query)
            conversations = result.scalars().all()

            recipients = []
            for conv in conversations:
                recipients.append({
                    "username": conv.lead.username,
                    "conversation_id": conv.id
                })

            return recipients

    except Exception as e:
        logger.error(f"❌ Ошибка получения получателей: {e}")
        return []


async def execute_broadcast(message: Message, session_id: int, recipients: list, broadcast_text: str):
    """Выполнение рассылки"""

    try:
        # Получаем сессию
        async with get_db() as db:
            session_result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = session_result.scalar_one()

        total_recipients = len(recipients)
        sent_count = 0
        failed_count = 0

        # Обновляем сообщение
        await message.edit_text(
            f"📤 <b>Рассылка в процессе...</b>\n\n"
            f"📊 Прогресс: 0/{total_recipients}\n"
            f"✅ Отправлено: 0\n"
            f"❌ Ошибок: 0"
        )

        for i, recipient in enumerate(recipients):
            try:
                # Отправляем сообщение
                success = await telegram_session_manager.send_message(
                    session_name=session.session_name,
                    username=recipient["username"],
                    message=broadcast_text
                )

                if success:
                    sent_count += 1
                    logger.info(f"📤 Рассылка: {session.session_name} → {recipient['username']}")
                else:
                    failed_count += 1
                    logger.error(f"❌ Ошибка рассылки: {session.session_name} → {recipient['username']}")

                # Обновляем прогресс каждые 5 сообщений
                if (i + 1) % 5 == 0 or i == total_recipients - 1:
                    progress_text = (
                        f"📤 <b>Рассылка в процессе...</b>\n\n"
                        f"📊 Прогресс: {i + 1}/{total_recipients}\n"
                        f"✅ Отправлено: {sent_count}\n"
                        f"❌ Ошибок: {failed_count}"
                    )

                    try:
                        await message.edit_text(progress_text)
                    except:
                        pass  # Игнорируем ошибки редактирования (слишком частые обновления)

                # Пауза между отправками
                await asyncio.sleep(3)

            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Ошибка отправки {recipient['username']}: {e}")

        # Финальный отчет
        final_text = f"""✅ <b>Рассылка завершена!</b>

📊 <b>Результаты:</b>
• Всего получателей: {total_recipients}
• Успешно отправлено: {sent_count}
• Ошибок: {failed_count}
• Успешность: {(sent_count / total_recipients * 100):.1f}%

🕐 <b>Время завершения:</b> {datetime.now().strftime('%H:%M:%S')}"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К рассылкам", callback_data="broadcast_main")
            ]]
        )

        await message.edit_text(final_text, reply_markup=keyboard)

        logger.success(f"✅ Рассылка завершена: {sent_count}/{total_recipients} успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка выполнения рассылки: {e}")

        error_text = f"""❌ <b>Ошибка рассылки</b>

Произошла ошибка при выполнении рассылки.
Отправлено: {sent_count}/{total_recipients}

Подробности в логах."""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К рассылкам", callback_data="broadcast_main")
            ]]
        )

        try:
            await message.edit_text(error_text, reply_markup=keyboard)
        except:
            pass


def get_filter_name(target_type: str) -> str:
    """Получение человекочитаемого названия фильтра"""
    filter_names = {
        "all": "Все диалоги",
        "with_ref": "С отправленной реф ссылкой",
        "without_ref": "Без отправленной реф ссылки"
    }
    return filter_names.get(target_type, target_type)


@broadcasts_router.callback_query(F.data == "broadcast_all")
async def broadcast_all_leads(callback: CallbackQuery):
    """Рассылка всем лидам"""

    try:
        async with get_db() as db:
            # Подсчитываем общее количество лидов
            total_result = await db.execute(
                select(func.count(Conversation.id))
                .where(Conversation.status == 'active')
            )
            total_leads = total_result.scalar() or 0

            # Группируем по сессиям
            sessions_result = await db.execute(
                select(
                    Session.session_name,
                    Session.id,
                    func.count(Conversation.id).label('leads_count')
                )
                .join(Conversation)
                .where(
                    Conversation.status == 'active',
                    Session.status == 'active'
                )
                .group_by(Session.id)
                .order_by(func.count(Conversation.id).desc())
            )
            sessions_stats = sessions_result.all()

        if not sessions_stats:
            await callback.answer("❌ Нет активных диалогов для рассылки")
            return

        text = f"""🎯 <b>Рассылка всем лидам</b>

📊 <b>Всего активных диалогов:</b> {total_leads}

📋 <b>Распределение по сессиям:</b>
"""

        for session in sessions_stats:
            text += f"• {session.session_name}: {session.leads_count} диалогов\n"

        text += f"""
⚠️ <b>Внимание:</b>
Рассылка будет выполнена через ВСЕ активные сессии.
Каждая сессия отправит сообщение своим лидам.

Продолжить?"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Продолжить", callback_data="broadcast_all_prepare"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка рассылки всем лидам: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@broadcasts_router.callback_query(F.data == "broadcast_all_prepare")
async def broadcast_all_prepare(callback: CallbackQuery, state: FSMContext):
    """Подготовка массовой рассылки"""

    await state.update_data(
        session_id="all",
        target_type="all"
    )

    text = """✏️ <b>Массовая рассылка всем лидам</b>

📝 Напишите сообщение, которое будет отправлено ВСЕМ активным лидам через ВСЕ сессии.

⚠️ <b>ВАЖНО:</b>
• Сообщение получат ВСЕ лиды во всех сессиях
• Каждая сессия отправит от своего имени
• Между отправками будут паузы для безопасности
• Это может занять много времени

Введите текст сообщения:"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_main")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(BroadcastStates.waiting_message)


@broadcasts_router.callback_query(F.data == "broadcast_status")
async def broadcast_status(callback: CallbackQuery):
    """Рассылка по статусу реф ссылки"""

    try:
        async with get_db() as db:
            # Статистика по статусам
            with_ref_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.ref_link_sent == True,
                    Conversation.status == 'active'
                )
            )
            with_ref = with_ref_result.scalar() or 0

            without_ref_result = await db.execute(
                select(func.count(Conversation.id))
                .where(
                    Conversation.ref_link_sent == False,
                    Conversation.status == 'active'
                )
            )
            without_ref = without_ref_result.scalar() or 0

        text = f"""🔗 <b>Рассылка по статусу реф ссылки</b>

📊 <b>Распределение активных лидов:</b>
• С отправленной ссылкой: {with_ref}
• Без отправленной ссылки: {without_ref}

Выберите целевую группу:"""

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🔗 С ссылкой ({with_ref})",
                        callback_data="broadcast_status_prepare_with_ref"
                    ),
                    InlineKeyboardButton(
                        text=f"📝 Без ссылки ({without_ref})",
                        callback_data="broadcast_status_prepare_without_ref"
                    )
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_main")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"❌ Ошибка рассылки по статусу: {e}")
        await callback.answer("❌ Ошибка загрузки данных")


@broadcasts_router.callback_query(F.data.startswith("broadcast_status_prepare_"))
async def broadcast_status_prepare(callback: CallbackQuery, state: FSMContext):
    """Подготовка рассылки по статусу"""

    status_type = callback.data.split("_")[-1]  # with_ref или without_ref

    await state.update_data(
        session_id="status",
        target_type=status_type
    )

    status_name = "с отправленной реф ссылкой" if status_type == "with_ref" else "без отправленной реф ссылки"

    text = f"""✏️ <b>Рассылка лидам {status_name}</b>

📝 Введите текст сообщения:

⚠️ <b>Важно:</b>
• Сообщение получат только лиды {status_name}
• Отправка будет выполнена через соответствующие сессии
• Между отправками будут паузы для безопасности

Введите ваш текст:"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_main")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(BroadcastStates.waiting_message)


@broadcasts_router.callback_query(F.data == "broadcast_history")
async def broadcast_history(callback: CallbackQuery):
    """История рассылок"""

    text = """📊 <b>История рассылок</b>

🚧 <b>Функция в разработке</b>

Здесь будет отображаться:
• Список выполненных рассылок
• Статистика доставки
• Результаты по конверсиям
• Ошибки доставки
• Временные метки

Планируется добавить в следующем обновлении."""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast_main")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


# Обработчик отмены для всех состояний
@broadcasts_router.message(lambda message: message.text == "/cancel")
async def cancel_broadcast(message: Message, state: FSMContext):
    """Отмена рассылки"""

    await state.clear()
    await message.answer(
        "❌ Рассылка отменена",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К рассылкам", callback_data="broadcast_main")
            ]]
        )
    )