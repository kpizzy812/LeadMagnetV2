from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from sqlalchemy import select, update
from storage.database import get_db
from storage.models.base import Conversation, Lead, Session
from loguru import logger


class ConversationFilter:
    """Система фильтрации диалогов"""

    def __init__(self):
        # Настройки фильтрации
        self.auto_approve_keywords = [
            "проект", "инвест", "заработок", "доход", "прибыль",
            "деньги", "крипта", "биткоин", "mining", "stake"
        ]

        self.blacklist_keywords = [
            "спам", "реклама", "продажа", "купить", "скидка",
            "промокод", "акция", "распродажа"
        ]

        # Белые списки (можно вынести в конфиг)
        self.whitelisted_usernames: Set[str] = set()
        self.blacklisted_usernames: Set[str] = set()

    async def should_respond_to_conversation(
            self,
            conversation: Conversation,
            message_text: str
    ) -> tuple[bool, str]:
        """
        Проверка нужно ли отвечать в диалоге

        Returns:
            (should_respond: bool, reason: str)
        """

        # 1. Проверка черного списка
        if conversation.is_blacklisted:
            return False, "Диалог в черном списке"

        if conversation.lead.username in self.blacklisted_usernames:
            return False, "Пользователь в черном списке"

        # 2. Белый список - всегда отвечаем
        if conversation.is_whitelisted:
            return True, "Диалог в белом списке"

        if conversation.lead.username in self.whitelisted_usernames:
            return True, "Пользователь в белом списке"

        # 3. Диалоги созданные вручную - всегда отвечаем
        if not conversation.auto_created:
            return True, "Диалог создан вручную"

        # 4. Проверка требует ли одобрения
        if conversation.requires_approval:
            return False, "Диалог требует одобрения"

        # 5. Проверка ключевых слов
        message_lower = message_text.lower()

        # Проверка на спам
        spam_count = sum(1 for keyword in self.blacklist_keywords
                         if keyword in message_lower)
        if spam_count >= 2:
            await self._auto_blacklist_conversation(conversation.id, "Обнаружен спам")
            return False, "Автоматически заблокирован как спам"

        # Проверка на релевантность
        relevant_count = sum(1 for keyword in self.auto_approve_keywords
                             if keyword in message_lower)
        if relevant_count >= 1:
            await self._auto_whitelist_conversation(conversation.id, "Релевантные ключевые слова")
            return True, "Автоматически одобрен по ключевым словам"

        # 6. Проверка активности диалога
        if conversation.messages_count >= 3:  # Если уже общались
            return True, "Диалог активный"

        # 7. По умолчанию - требует одобрения для новых диалогов
        await self._set_requires_approval(conversation.id, True)
        return False, "Новый диалог требует одобрения"

    async def _auto_blacklist_conversation(self, conversation_id: int, reason: str):
        """Автоматическое добавление в черный список"""
        try:
            async with get_db() as db:
                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(is_blacklisted=True)
                )
                await db.commit()

            logger.warning(f"🚫 Диалог {conversation_id} добавлен в черный список: {reason}")

        except Exception as e:
            logger.error(f"❌ Ошибка добавления в черный список: {e}")

    async def _auto_whitelist_conversation(self, conversation_id: int, reason: str):
        """Автоматическое добавление в белый список"""
        try:
            async with get_db() as db:
                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(
                        is_whitelisted=True,
                        requires_approval=False
                    )
                )
                await db.commit()

            logger.info(f"✅ Диалог {conversation_id} добавлен в белый список: {reason}")

        except Exception as e:
            logger.error(f"❌ Ошибка добавления в белый список: {e}")

    async def _set_requires_approval(self, conversation_id: int, requires: bool):
        """Установка флага требования одобрения"""
        try:
            async with get_db() as db:
                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(requires_approval=requires)
                )
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка установки флага одобрения: {e}")


# Глобальный экземпляр фильтра
conversation_filter = ConversationFilter()