# cold_outreach/templates/channel_post_manager.py

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import Message as TelegramMessage, Channel
from sqlalchemy import select, update

from storage.database import get_db
from storage.models.cold_outreach import OutreachTemplate
from core.integrations.telegram_client import telegram_session_manager
from loguru import logger


class ChannelPostManager:
    """Менеджер постов из каналов для рассылки"""

    def __init__(self):
        self.channel_cache: Dict[str, Dict] = {}
        self.post_cache: Dict[str, List[Dict]] = {}

    async def initialize(self):
        """Инициализация менеджера постов"""
        logger.info("✅ ChannelPostManager инициализирован")

    async def create_post_template(
            self,
            name: str,
            description: str,
            channel_username: str,
            post_id: Optional[int] = None,
            use_latest_post: bool = True,
            category: str = "channel_post",
            created_by: str = None
    ) -> Optional[int]:
        """Создание шаблона на основе поста из канала"""

        try:
            # Получаем пост из канала
            post_data = await self._get_channel_post(channel_username, post_id, use_latest_post)

            if not post_data:
                logger.error(f"❌ Не удалось получить пост из канала @{channel_username}")
                return None

            # Формируем специальный текст шаблона для пересылки
            template_text = f"[FORWARD_POST:{channel_username}:{post_data['message_id']}]"

            async with get_db() as db:
                template = OutreachTemplate(
                    name=name,
                    description=description,
                    text=template_text,
                    variables=[],  # У постов нет переменных
                    category=category,
                    enable_ai_uniquification=False,  # Посты не уникализируем
                    created_by=created_by,
                    # Дополнительные поля для постов
                    extra_data={
                        "is_channel_post": True,
                        "channel_username": channel_username,
                        "original_post_id": post_data['message_id'],
                        "post_text": post_data.get('text'),
                        "has_media": post_data.get('has_media', False),
                        "media_type": post_data.get('media_type'),
                        "has_buttons": post_data.get('has_buttons', False),
                        "use_latest_post": use_latest_post
                    }
                )

                db.add(template)
                await db.flush()
                await db.refresh(template)

                template_id = template.id
                await db.commit()

                logger.info(f"✅ Создан шаблон поста '{name}' с ID {template_id}")
                return template_id

        except Exception as e:
            logger.error(f"❌ Ошибка создания шаблона поста: {e}")
            return None

    async def _get_channel_post(
            self,
            channel_username: str,
            post_id: Optional[int] = None,
            use_latest: bool = True
    ) -> Optional[Dict]:
        """Получение поста из канала"""

        try:
            # Получаем любую доступную сессию для проверки канала
            session_names = await telegram_session_manager.get_active_sessions()
            if not session_names:
                logger.error("❌ Нет активных сессий для проверки канала")
                return None

            session_name = session_names[0]
            client = await telegram_session_manager.get_client(session_name)

            if not client:
                logger.error(f"❌ Не удалось получить клиент {session_name}")
                return None

            # Подписываемся на канал если не подписаны
            try:
                channel = await client.get_entity(channel_username)

                # Проверяем подписку
                try:
                    await client.get_permissions(channel)
                except:
                    # Пытаемся подписаться
                    await client(JoinChannelRequest(channel))
                    logger.info(f"📱 Подписались на канал @{channel_username}")

            except Exception as e:
                logger.error(f"❌ Ошибка доступа к каналу @{channel_username}: {e}")
                return None

            # Получаем сообщения
            if use_latest or post_id is None:
                # Получаем последний пост
                messages = await client.get_messages(channel, limit=1)
                if not messages:
                    return None
                message = messages[0]
            else:
                # Получаем конкретный пост
                message = await client.get_messages(channel, ids=post_id)
                if not message or isinstance(message, list):
                    return None

            # Извлекаем данные поста
            post_data = {
                "message_id": message.id,
                "text": message.text or "",
                "date": message.date,
                "has_media": bool(message.media),
                "media_type": None,
                "has_buttons": bool(message.reply_markup),
                "views": getattr(message, 'views', 0),
                "channel_username": channel_username
            }

            # Определяем тип медиа
            if message.media:
                if hasattr(message.media, 'photo'):
                    post_data["media_type"] = "photo"
                elif hasattr(message.media, 'document'):
                    post_data["media_type"] = "document"
                elif hasattr(message.media, 'video'):
                    post_data["media_type"] = "video"
                else:
                    post_data["media_type"] = "other"

            return post_data

        except Exception as e:
            logger.error(f"❌ Ошибка получения поста из канала: {e}")
            return None

    async def send_channel_post(
            self,
            session_name: str,
            username: str,
            template: OutreachTemplate
    ) -> bool:
        """Отправка поста из канала пользователю"""

        try:
            # Проверяем что это шаблон поста
            if not self._is_channel_post_template(template):
                logger.error(f"❌ Шаблон {template.id} не является шаблоном поста")
                return False

            # Получаем данные о посте
            extra_data = template.extra_data or {}
            channel_username = extra_data.get("channel_username")
            use_latest_post = extra_data.get("use_latest_post", False)
            original_post_id = extra_data.get("original_post_id")

            if not channel_username:
                logger.error(f"❌ В шаблоне {template.id} не указан канал")
                return False

            # Получаем клиент сессии
            client = await telegram_session_manager.get_client(session_name)
            if not client:
                logger.error(f"❌ Не удалось получить клиент {session_name}")
                return False

            # Определяем какой пост пересылать
            if use_latest_post:
                # Получаем последний пост
                channel = await client.get_entity(channel_username)
                messages = await client.get_messages(channel, limit=1)
                if not messages:
                    logger.error(f"❌ Нет сообщений в канале @{channel_username}")
                    return False
                message_to_forward = messages[0]
            else:
                # Пересылаем конкретный пост
                channel = await client.get_entity(channel_username)
                message_to_forward = await client.get_messages(channel, ids=original_post_id)
                if not message_to_forward:
                    logger.error(f"❌ Пост {original_post_id} не найден в @{channel_username}")
                    return False

            # Пересылаем пост
            await client.forward_messages(
                entity=username,
                messages=message_to_forward,
                from_peer=channel
            )

            logger.info(f"📤 Пост переслан: {session_name} → @{username} из @{channel_username}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка пересылки поста: {e}")
            return False

    def _is_channel_post_template(self, template: OutreachTemplate) -> bool:
        """Проверка является ли шаблон постом из канала"""

        # Проверяем по специальному формату текста
        if template.text.startswith("[FORWARD_POST:"):
            return True

        # Проверяем по метаданным
        extra_data = template.extra_data or {}
        return extra_data.get("is_channel_post", False)

    async def get_channel_posts_preview(
            self,
            channel_username: str,
            limit: int = 10
    ) -> List[Dict]:
        """Получение превью постов из канала"""

        try:
            # Получаем клиент
            session_names = await telegram_session_manager.get_active_sessions()
            if not session_names:
                return []

            client = await telegram_session_manager.get_client(session_names[0])
            if not client:
                return []

            # Получаем канал
            channel = await client.get_entity(channel_username)

            # Получаем последние посты
            messages = await client.get_messages(channel, limit=limit)

            posts_preview = []
            for msg in messages:
                preview = {
                    "message_id": msg.id,
                    "text": (msg.text or "")[:200] + "..." if len(msg.text or "") > 200 else (msg.text or ""),
                    "date": msg.date.strftime("%d.%m.%Y %H:%M"),
                    "has_media": bool(msg.media),
                    "media_type": self._get_media_type(msg),
                    "has_buttons": bool(msg.reply_markup),
                    "views": getattr(msg, 'views', 0)
                }
                posts_preview.append(preview)

            return posts_preview

        except Exception as e:
            logger.error(f"❌ Ошибка получения превью постов: {e}")
            return []

    def _get_media_type(self, message) -> Optional[str]:
        """Определение типа медиа в сообщении"""

        if not message.media:
            return None

        if hasattr(message.media, 'photo'):
            return "📷 Фото"
        elif hasattr(message.media, 'document'):
            if message.media.document.mime_type.startswith('video'):
                return "🎥 Видео"
            elif message.media.document.mime_type.startswith('audio'):
                return "🎵 Аудио"
            else:
                return "📎 Файл"
        else:
            return "📎 Медиа"

    async def refresh_channel_cache(self, channel_username: str):
        """Обновление кэша канала"""

        try:
            posts = await self.get_channel_posts_preview(channel_username, 50)
            self.post_cache[channel_username] = posts

            logger.info(f"🔄 Кэш канала @{channel_username} обновлен: {len(posts)} постов")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления кэша канала: {e}")

    async def auto_join_channel(self, session_name: str, channel_username: str) -> bool:
        """Автоматическое вступление в канал"""

        try:
            client = await telegram_session_manager.get_client(session_name)
            if not client:
                return False

            # Пытаемся вступить в канал
            from telethon.tl.functions.channels import JoinChannelRequest

            channel = await client.get_entity(channel_username)
            await client(JoinChannelRequest(channel))

            logger.info(f"✅ Сессия {session_name} вступила в @{channel_username}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка вступления в канал: {e}")
            return False

    async def validate_channel_access(self, channel_username: str) -> Dict[str, Any]:
        """Проверка доступа к каналу"""

        try:
            session_names = await telegram_session_manager.get_active_sessions()
            if not session_names:
                return {"valid": False, "error": "Нет активных сессий"}

            client = await telegram_session_manager.get_client(session_names[0])
            if not client:
                return {"valid": False, "error": "Не удалось получить клиент"}

            # Проверяем канал
            try:
                channel = await client.get_entity(channel_username)

                # Проверяем права доступа
                permissions = await client.get_permissions(channel)

                # Пробуем получить последний пост
                messages = await client.get_messages(channel, limit=1)

                return {
                    "valid": True,
                    "channel_title": getattr(channel, 'title', 'Unknown'),
                    "subscribers_count": getattr(channel, 'participants_count', 0),
                    "can_read": bool(messages),
                    "recent_posts": len(messages)
                }

            except Exception as e:
                return {"valid": False, "error": f"Ошибка доступа: {str(e)}"}

        except Exception as e:
            return {"valid": False, "error": f"Критическая ошибка: {str(e)}"}


# Глобальный экземпляр менеджера постов
channel_post_manager = ChannelPostManager()