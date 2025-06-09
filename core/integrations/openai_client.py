# core/integrations/openai_client.py

import asyncio
from typing import List, Dict, Any, Optional
import tiktoken
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from config.settings.base import settings
from loguru import logger


class OpenAIClient:
    """Клиент для работы с OpenAI API"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai.api_key)
        self.model = settings.openai.model
        self.max_tokens = settings.openai.max_tokens
        self.temperature = settings.openai.temperature

        # Для подсчета токенов
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    async def generate_response(
            self,
            messages: List[Dict[str, str]],
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            timeout: int = 30
    ) -> Optional[str]:
        """Генерация ответа через OpenAI"""

        try:
            # Проверяем количество токенов
            total_tokens = self._count_tokens(messages)
            if total_tokens > 15000:  # Оставляем место для ответа
                messages = self._trim_messages(messages, max_tokens=12000)
                logger.warning(f"⚠️ Обрезаны сообщения: {total_tokens} → {self._count_tokens(messages)} токенов")

            # Параметры запроса
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens,
                "timeout": timeout
            }

            # Отправляем запрос
            start_time = asyncio.get_event_loop().time()

            response: ChatCompletion = await self.client.chat.completions.create(**request_params)

            processing_time = asyncio.get_event_loop().time() - start_time

            # Извлекаем ответ
            if response.choices and response.choices[0].message:
                content = response.choices[0].message.content

                # Логируем статистику
                tokens_used = response.usage.total_tokens if response.usage else 0
                logger.info(
                    f"🤖 OpenAI ответ: {tokens_used} токенов, "
                    f"{processing_time:.2f}с, модель: {self.model}"
                )

                return content

            logger.warning("⚠️ OpenAI вернул пустой ответ")
            return None

        except asyncio.TimeoutError:
            logger.error(f"⏰ Таймаут)