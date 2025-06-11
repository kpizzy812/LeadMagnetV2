# cold_outreach/bot_handlers/channel_post_handlers.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from cold_outreach.templates.channel_post_manager import channel_post_manager
from cold_outreach.templates.template_manager import template_manager
from loguru import logger

channel_post_router = Router()


class ChannelPostStates(StatesGroup):
    """Состояния для создания шаблонов из постов каналов"""
    waiting_template_name = State()
    waiting_channel_username = State()
    waiting_post_selection = State()


@channel_post_router.callback_query(F.data == "templates_create_from_channel")
async def create_template_from_channel_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания шаблона из поста канала"""

    text = """📺 <b>Создание шаблона из поста канала</b>

🔗 <b>Как это работает:</b>
• Вы указываете канал и пост
• Система будет пересылать этот пост лидам
• Медиа, кнопки и форматирование сохранятся

📝 Введите название для шаблона:

Например: "Пост о новом проекте", "Реклама канала", "Анонс события"

💡 Название поможет различать шаблоны в списке."""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_templates")
        ]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(ChannelPostStates.waiting_template_name)


@channel_post_router.message(ChannelPostStates.waiting_template_name)
async def create_template_from_channel_name(message: Message, state: FSMContext):
    """Получение названия шаблона поста"""

    template_name = message.text.strip()

    if not template_name or len(template_name) < 3:
        await message.answer("❌ Название должно содержать минимум 3 символа. Попробуйте еще раз:")
        return

    await state.update_data(template_name=template_name)

    text = f"""📺 <b>Шаблон: "{template_name}"</b>

📺 Теперь введите username канала:

<b>Примеры:</b>
• <code>@channel_name</code>
• <code>channel_name</code> (без @)

⚠️ <b>Требования:</b>
• Канал должен быть доступен для чтения
• Ваши сессии должны быть подписаны на канал
• Или канал должен быть публичным

💡 <b>Совет:</b> Для приватных каналов сначала подпишите сессии вручную."""

    await message.answer(text)
    await state.set_state(ChannelPostStates.waiting_channel_username)


@channel_post_router.message(ChannelPostStates.waiting_channel_username)
async def create_template_from_channel_username(message: Message, state: FSMContext):
    """Получение username канала"""

    channel_input = message.text.strip()

    # Нормализуем username канала
    channel_username = channel_input.lstrip("@")

    if not channel_username:
        await message.answer("❌ Введите корректный username канала. Попробуйте еще раз:")
        return

    await state.update_data(channel_username=channel_username)

    # Показываем индикатор загрузки
    loading_msg = await message.answer("🔍 Проверяем доступ к каналу...")

    try:
        # Проверяем доступ к каналу
        validation = await channel_post_manager.validate_channel_access(channel_username)

        if not validation["valid"]:
            await loading_msg.edit_text(
                f"❌ <b>Ошибка доступа к каналу</b>\n\n"
                f"🔗 Канал: @{channel_username}\n"
                f"❌ Причина: {validation['error']}\n\n"
                f"💡 <b>Что проверить:</b>\n"
                f"• Канал существует и доступен\n"
                f"• Ваши сессии подписаны на канал\n"
                f"• Канал не заблокирован для ботов"
            )
            return

        # Получаем превью постов
        posts_preview = await channel_post_manager.get_channel_posts_preview(channel_username, 5)

        if not posts_preview:
            await loading_msg.edit_text(
                f"❌ <b>В канале нет доступных постов</b>\n\n"
                f"🔗 Канал: @{channel_username}\n"
                f"📊 Подписчиков: {validation.get('subscribers_count', 'N/A')}"
            )
            return

        # Формируем текст с превью
        text = f"""✅ <b>Канал найден: @{channel_username}</b>

📊 <b>Информация:</b>
• Название: {validation.get('channel_title', 'N/A')}
• Подписчиков: {validation.get('subscribers_count', 'N/A')}
• Доступных постов: {len(posts_preview)}

📝 <b>Последние посты:</b>
"""

        keyboard_buttons = []

        for i, post in enumerate(posts_preview):
            # Краткое описание поста
            post_desc = f"#{post['message_id']}"
            if post['has_media']:
                post_desc += f" {post['media_type']}"
            if post['text']:
                post_desc += f" - {post['text'][:30]}..."
            else:
                post_desc += " - [без текста]"

            text += f"\n{i + 1}. {post_desc}"
            text += f"\n   📅 {post['date']} | 👁 {post['views']}\n"

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📝 Пост #{post['message_id']} ({post['date']})",
                    callback_data=f"select_post_{post['message_id']}"
                )
            ])

        # Добавляем опцию "последний пост"
        keyboard_buttons.insert(0, [
            InlineKeyboardButton(
                text="🔄 Всегда последний пост",
                callback_data="select_post_latest"
            )
        ])

        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data="outreach_templates")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await loading_msg.edit_text(text, reply_markup=keyboard)
        await state.set_state(ChannelPostStates.waiting_post_selection)

    except Exception as e:
        logger.error(f"❌ Ошибка проверки канала: {e}")
        await loading_msg.edit_text(
            f"❌ <b>Ошибка при проверке канала</b>\n\n"
            f"Технические детали: {str(e)}"
        )


@channel_post_router.callback_query(F.data.startswith("select_post_"), ChannelPostStates.waiting_post_selection)
async def create_template_from_channel_post_selected(callback: CallbackQuery, state: FSMContext):
    """Выбор поста из канала"""

    try:
        data = await state.get_data()
        template_name = data["template_name"]
        channel_username = data["channel_username"]

        post_selection = callback.data.replace("select_post_", "")

        # Определяем параметры поста
        if post_selection == "latest":
            use_latest_post = True
            post_id = None
            post_desc = "всегда последний пост"
        else:
            use_latest_post = False
            post_id = int(post_selection)
            post_desc = f"пост #{post_id}"

        # Показываем индикатор создания
        await callback.message.edit_text("⏳ Создаем шаблон поста...")

        # Создаем шаблон
        template_id = await template_manager.create_template(
            name=template_name,
            text="",  # Для постов текст не нужен
            description=f"Пост из канала @{channel_username} ({post_desc})",
            category="channel_post",
            is_channel_post=True,