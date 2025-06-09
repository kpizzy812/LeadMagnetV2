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
        self.client: Optional[AsyncOpenAI] = None
        self.model = settings.openai.model
        self.max_tokens = settings.openai.max_tokens
        self.temperature = settings.openai.temperature
        self.encoding = None

        # Инициализируем только если есть API ключ
        self._initialize()


# core/integrations/openai_client.py

import asyncio
from typing import List, Dict, Any, Optional
import tiktoken
from openai import AsyncOpenAI

from config.settings.base import settings
from loguru import logger


class OpenAIClient:
    """Клиент для работы с OpenAI API"""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        self.model = settings.openai.model
        self.max_tokens = settings.openai.max_tokens
        self.temperature = settings.openai.temperature
        self.encoding = None

        # Инициализируем только если есть API ключ
        self._initialize()

    def _initialize(self):
        """Безопасная инициализация клиента"""
        try:
            api_key = settings.openai.api_key

            # Проверяем что API ключ корректный
            if not api_key or api_key in ["", "sk-your-openai-api-key"]:
                logger.warning("⚠️ OpenAI API ключ не настроен")
                return

            # Создаем клиент с базовыми параметрами
            self.client = AsyncOpenAI(api_key=api_key)

            # Для подсчета токенов
            try:
                self.encoding = tiktoken.encoding_for_model(self.model)
            except KeyError:
                self.encoding = tiktoken.get_encoding("cl100k_base")

            logger.info(f"✅ OpenAI клиент инициализирован (модель: {self.model})")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации OpenAI клиента: {e}")
            self.client = None

    async def generate_response(
            self,
            messages: List[Dict[str, str]],
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            timeout: int = 30
    ) -> Optional[str]:
        """Генерация ответа через OpenAI"""

        if not self.client:
            logger.error("❌ OpenAI клиент не инициализирован")
            return None

        try:
            # Проверяем количество токенов
            total_tokens = self._count_tokens(messages)
            if total_tokens > 15000:  # Оставляем место для ответа
                messages = self._trim_messages(messages, max_tokens=12000)
                logger.warning(f"⚠️ Обрезаны сообщения: {total_tokens} → {self._count_tokens(messages)} токенов")

            start_time = asyncio.get_event_loop().time()

            # Создаем запрос
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens
            )

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

        except Exception as e:
            logger.error(f"❌ Ошибка OpenAI запроса: {e}")
            return None

    def _count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Подсчет токенов в сообщениях"""
        if not self.encoding:
            # Грубая оценка: ~4 символа = 1 токен
            return sum(len(msg.get("content", "")) for msg in messages) // 4

        try:
            total_tokens = 0
            for message in messages:
                # Примерный подсчет токенов для ChatGPT
                total_tokens += len(self.encoding.encode(message.get("content", "")))
                total_tokens += 4  # Каждое сообщение добавляет ~4 токена метаданных

            total_tokens += 2  # Дополнительные токены для ответа
            return total_tokens

        except Exception as e:
            logger.error(f"❌ Ошибка подсчета токенов: {e}")
            # Грубая оценка: ~4 символа = 1 токен
            return sum(len(msg.get("content", "")) for msg in messages) // 4

    def _trim_messages(self, messages: List[Dict[str, str]], max_tokens: int = 12000) -> List[Dict[str, str]]:
        """Обрезка сообщений до лимита токенов"""
        if not messages or not self.encoding:
            return messages

        # Всегда сохраняем системное сообщение
        system_message = messages[0] if messages[0].get("role") == "system" else None
        conversation_messages = messages[1:] if system_message else messages

        trimmed_messages = []
        current_tokens = 0

        # Добавляем системное сообщение
        if system_message:
            system_tokens = len(self.encoding.encode(system_message.get("content", "")))
            if system_tokens < max_tokens:
                trimmed_messages.append(system_message)
                current_tokens += system_tokens

        # Добавляем сообщения с конца (самые новые)
        for message in reversed(conversation_messages):
            message_tokens = len(self.encoding.encode(message.get("content", ""))) + 4

            if current_tokens + message_tokens > max_tokens:
                break

            trimmed_messages.insert(-1 if system_message else 0, message)
            current_tokens += message_tokens

        return trimmed_messages

    async def health_check(self) -> bool:
        """Проверка здоровья OpenAI API"""
        if not self.client:
            return False

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )

            return bool(response.choices)

        except Exception as e:
            logger.error(f"❌ Health check OpenAI провален: {e}")
            return False

    async def test_connection(self) -> Dict[str, Any]:
        """Тестирование соединения с подробной информацией"""
        if not self.client:
            return {
                "success": False,
                "error": "Клиент не инициализирован",
                "model": self.model
            }

        try:
            start_time = asyncio.get_event_loop().time()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=50
            )

            processing_time = asyncio.get_event_loop().time() - start_time

            return {
                "success": True,
                "model": self.model,
                "processing_time": round(processing_time, 2),
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "response_length": len(response.choices[0].message.content) if response.choices else 0
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model": self.model
            }


# Создаем глобальный экземпляр безопасно
try:
    openai_client = OpenAIClient()
except Exception as e:
    logger.error(f"❌ Не удалось создать OpenAI клиент: {e}")


    # Создаем заглушку
    class DummyOpenAIClient:
        async def generate_response(self, *args, **kwargs):
            return None

        async def health_check(self):
            return False

        async def test_connection(self):
            return {"success": False, "error": "Client not initialized"}


    openai_client = DummyOpenAIClient()


    async def generate_response(
            self,
            messages: List[Dict[str, str]],
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            timeout: int = 30
    ) -> Optional[str]:
        """Генерация ответа через OpenAI"""

        if not self.client:
            logger.error("❌ OpenAI клиент не инициализирован")
            return None

        try:
            # Проверяем количество токенов
            total_tokens = self._count_tokens(messages)
            if total_tokens > 15000:  # Оставляем место для ответа
                messages = self._trim_messages(messages, max_tokens=12000)
                logger.warning(f"⚠️ Обрезаны сообщения: {total_tokens} → {self._count_tokens(messages)} токенов")

            # Параметры запроса для актуальной версии
            start_time = asyncio.get_event_loop().time()

            response: ChatCompletion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens
            )

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
            logger.error(f"⏰ Таймаут OpenAI запроса ({timeout}с)")
            return None

        except Exception as e:
            logger.error(f"❌ Ошибка OpenAI запроса: {e}")
            return None


    def _count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Подсчет токенов в сообщениях"""
        if not self.encoding:
            # Грубая оценка: ~4 символа = 1 токен
            return sum(len(msg.get("content", "")) for msg in messages) // 4

        try:
            total_tokens = 0
            for message in messages:
                # Примерный подсчет токенов для ChatGPT
                total_tokens += len(self.encoding.encode(message.get("content", "")))
                total_tokens += 4  # Каждое сообщение добавляет ~4 токена метаданных

            total_tokens += 2  # Дополнительные токены для ответа
            return total_tokens

        except Exception as e:
            logger.error(f"❌ Ошибка подсчета токенов: {e}")
            # Грубая оценка: ~4 символа = 1 токен
            return sum(len(msg.get("content", "")) for msg in messages) // 4


    def _trim_messages(self, messages: List[Dict[str, str]], max_tokens: int = 12000) -> List[Dict[str, str]]:
        """Обрезка сообщений до лимита токенов"""
        if not messages or not self.encoding:
            return messages

        # Всегда сохраняем системное сообщение
        system_message = messages[0] if messages[0].get("role") == "system" else None
        conversation_messages = messages[1:] if system_message else messages

        trimmed_messages = []
        current_tokens = 0

        # Добавляем системное сообщение
        if system_message:
            system_tokens = len(self.encoding.encode(system_message.get("content", "")))
            if system_tokens < max_tokens:
                trimmed_messages.append(system_message)
                current_tokens += system_tokens

        # Добавляем сообщения с конца (самые новые)
        for message in reversed(conversation_messages):
            message_tokens = len(self.encoding.encode(message.get("content", ""))) + 4

            if current_tokens + message_tokens > max_tokens:
                break

            trimmed_messages.insert(-1 if system_message else 0, message)
            current_tokens += message_tokens

        return trimmed_messages


    async def health_check(self) -> bool:
        """Проверка здоровья OpenAI API"""
        if not self.client:
            return False

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )

            return bool(response.choices)

        except Exception as e:
            logger.error(f"❌ Health check OpenAI провален: {e}")
            return False


    async def test_connection(self) -> Dict[str, Any]:
        """Тестирование соединения с подробной информацией"""
        if not self.client:
            return {
                "success": False,
                "error": "Клиент не инициализирован",
                "model": self.model
            }

        try:
            start_time = asyncio.get_event_loop().time()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=50
            )

            processing_time = asyncio.get_event_loop().time() - start_time

            return {
                "success": True,
                "model": self.model,
                "processing_time": round(processing_time, 2),
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "response_length": len(response.choices[0].message.content) if response.choices else 0
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model": self.model
            }

# Создаем глобальный экземпляр безопасно
try:
    openai_client = OpenAIClient()
except Exception as e:
    logger.error(f"❌ Не удалось создать OpenAI клиент: {e}")


    # Создаем заглушку
    class DummyOpenAIClient:
        async def generate_response(self, *args, **kwargs):
            return None

        async def health_check(self):
            return False

        async def test_connection(self):
            return {"success": False, "error": "Client not initialized"}


    openai_client = DummyOpenAIClient()


    async def generate_response(
            self,
            messages: List[Dict[str, str]],
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            timeout: int = 30
    ) -> Optional[str]:
        """Генерация ответа через OpenAI"""

        if not self.client:
            logger.error("❌ OpenAI клиент не инициализирован")
            return None

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
            logger.error(f"⏰ Таймаут OpenAI запроса ({timeout}с)")
            return None

        except Exception as e:
            logger.error(f"❌ Ошибка OpenAI запроса: {e}")
            return None


    def _count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Подсчет токенов в сообщениях"""
        if not self.encoding:
            # Грубая оценка: ~4 символа = 1 токен
            return sum(len(msg.get("content", "")) for msg in messages) // 4

        try:
            total_tokens = 0
            for message in messages:
                # Примерный подсчет токенов для ChatGPT
                total_tokens += len(self.encoding.encode(message.get("content", "")))
                total_tokens += 4  # Каждое сообщение добавляет ~4 токена метаданных

            total_tokens += 2  # Дополнительные токены для ответа
            return total_tokens

        except Exception as e:
            logger.error(f"❌ Ошибка подсчета токенов: {e}")
            # Грубая оценка: ~4 символа = 1 токен
            return sum(len(msg.get("content", "")) for msg in messages) // 4


    def _trim_messages(self, messages: List[Dict[str, str]], max_tokens: int = 12000) -> List[Dict[str, str]]:
        """Обрезка сообщений до лимита токенов"""
        if not messages or not self.encoding:
            return messages

        # Всегда сохраняем системное сообщение
        system_message = messages[0] if messages[0].get("role") == "system" else None
        conversation_messages = messages[1:] if system_message else messages

        trimmed_messages = []
        current_tokens = 0

        # Добавляем системное сообщение
        if system_message:
            system_tokens = len(self.encoding.encode(system_message.get("content", "")))
            if system_tokens < max_tokens:
                trimmed_messages.append(system_message)
                current_tokens += system_tokens

        # Добавляем сообщения с конца (самые новые)
        for message in reversed(conversation_messages):
            message_tokens = len(self.encoding.encode(message.get("content", ""))) + 4

            if current_tokens + message_tokens > max_tokens:
                break

            trimmed_messages.insert(-1 if system_message else 0, message)
            current_tokens += message_tokens

        return trimmed_messages


    async def health_check(self) -> bool:
        """Проверка здоровья OpenAI API"""
        if not self.client:
            return False

        try:
            test_messages = [
                {"role": "user", "content": "Test"}
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=test_messages,
                max_tokens=10,
                timeout=10
            )

            return bool(response.choices)

        except Exception as e:
            logger.error(f"❌ Health check OpenAI провален: {e}")
            return False


    async def test_connection(self) -> Dict[str, Any]:
        """Тестирование соединения с подробной информацией"""
        if not self.client:
            return {
                "success": False,
                "error": "Клиент не инициализирован",
                "model": self.model
            }

        try:
            start_time = asyncio.get_event_loop().time()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=50,
                timeout=15
            )

            processing_time = asyncio.get_event_loop().time() - start_time

            return {
                "success": True,
                "model": self.model,
                "processing_time": round(processing_time, 2),
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "response_length": len(response.choices[0].message.content) if response.choices else 0
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model": self.model
            }


# Глобальный экземпляр клиента - создаем безопасно
def create_openai_client():
    """Безопасное создание клиента"""
    try:
        return OpenAIClient()
    except Exception as e:
        logger.error(f"❌ Не удалось создать OpenAI клиент: {e}")

        # Возвращаем заглушку
        class DummyClient:
            async def generate_response(self, *args, **kwargs):
                return None

            async def health_check(self):
                return False

            async def test_connection(self):
                return {"success": False, "error": "Client not initialized"}

        return DummyClient()


openai_client = create_openai_client()