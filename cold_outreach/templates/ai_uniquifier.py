# cold_outreach/templates/ai_uniquifier.py

import hashlib
from typing import Dict, List, Optional, Any
from core.integrations.openai_client import openai_client
from loguru import logger


class AIUniquifier:
    """ИИ уникализатор сообщений для избежания одинаковых текстов"""

    def __init__(self):
        self.uniquification_cache: Dict[str, str] = {}
        self.max_cache_size = 1000

    async def initialize(self):
        """Инициализация AI Uniquifier"""
        logger.info("✅ AIUniquifier инициализирован")

    async def uniquify_message(
            self,
            message_text: str,
            level: str = "medium",
            lead_data: Dict[str, Any] = None
    ) -> str:
        """Уникализация сообщения с помощью ИИ"""

        try:
            # Проверяем кэш
            cache_key = self._get_cache_key(message_text, level)
            if cache_key in self.uniquification_cache:
                logger.debug("🔄 Использован кэшированный вариант уникализации")
                return self.uniquification_cache[cache_key]

            # Генерируем уникальный вариант
            unique_message = await self._generate_unique_variant(
                message_text, level, lead_data
            )

            if unique_message and unique_message != message_text:
                # Сохраняем в кэш
                self._add_to_cache(cache_key, unique_message)
                logger.debug(f"✨ Сообщение уникализировано (уровень: {level})")
                return unique_message
            else:
                logger.warning("⚠️ Не удалось уникализировать сообщение")
                return message_text

        except Exception as e:
            logger.error(f"❌ Ошибка уникализации сообщения: {e}")
            return message_text

    async def _generate_unique_variant(
            self,
            message_text: str,
            level: str,
            lead_data: Dict[str, Any] = None
    ) -> Optional[str]:
        """Генерация уникального варианта сообщения"""

        try:
            # Формируем промпт в зависимости от уровня
            system_prompt = self._get_system_prompt(level)
            user_prompt = self._build_user_prompt(message_text, level, lead_data)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Генерируем ответ
            response = await openai_client.generate_response(
                messages=messages,
                temperature=0.7,  # Больше креативности
                max_tokens=800
            )

            if response:
                # Очищаем ответ от лишнего
                cleaned_response = self._clean_response(response)
                return cleaned_response

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка генерации уникального варианта: {e}")
            return None

    def _get_system_prompt(self, level: str) -> str:
        """Получение системного промпта в зависимости от уровня"""

        base_prompt = """Ты эксперт по написанию персональных сообщений для холодных обращений в Telegram. 
Твоя задача - перефразировать сообщение, сохранив его смысл и цель, но изменив формулировки.

ВАЖНЫЕ ПРАВИЛА:
- Сохрани основную идею и призыв к действию
- Используй естественный разговорный стиль
- Сообщение должно звучать как написанное реальным человеком
- НЕ добавляй лишнюю информацию
- НЕ меняй переменные в фигурных скобках {variable}
- НЕ делай сообщение слишком формальным
- Ответь ТОЛЬКО перефразированным текстом без пояснений"""

        level_instructions = {
            "light": """
УРОВЕНЬ ИЗМЕНЕНИЙ: ЛЁГКИЙ
- Измени порядок слов в предложениях
- Замени некоторые слова синонимами
- Добавь/убери пару слов для естественности
- Сохрани структуру сообщения""",

            "medium": """
УРОВЕНЬ ИЗМЕНЕНИЙ: СРЕДНИЙ  
- Перефразируй предложения, сохранив смысл
- Измени структуру некоторых предложений
- Используй другие выражения для той же идеи
- Можешь слегка изменить тон (но оставь дружелюбным)""",

            "heavy": """
УРОВЕНЬ ИЗМЕНЕНИЙ: СИЛЬНЫЙ
- Полностью перепиши сообщение другими словами
- Измени структуру и подачу информации
- Используй альтернативный подход к убеждению
- Сохрани только суть и цель сообщения"""
        }

        return base_prompt + "\n\n" + level_instructions.get(level, level_instructions["medium"])

    def _build_user_prompt(
            self,
            message_text: str,
            level: str,
            lead_data: Dict[str, Any] = None
    ) -> str:
        """Построение пользовательского промпта"""

        prompt = f"Перефразируй это сообщение:\n\n{message_text}"

        # Добавляем контекст о лиде если есть
        if lead_data:
            context_parts = []

            if lead_data.get("username"):
                context_parts.append(f"получатель: @{lead_data['username']}")

            if lead_data.get("first_name"):
                context_parts.append(f"имя: {lead_data['first_name']}")

            if context_parts:
                prompt += f"\n\nКонтекст: {', '.join(context_parts)}"

        return prompt

    def _clean_response(self, response: str) -> str:
        """Очистка ответа от ИИ"""

        try:
            # Убираем лишние пробелы и переводы строк
            cleaned = response.strip()

            # Убираем возможные обертки в кавычки
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]

            if cleaned.startswith("'") and cleaned.endswith("'"):
                cleaned = cleaned[1:-1]

            # Убираем возможные комментарии ИИ
            lines = cleaned.split('\n')
            content_lines = []

            for line in lines:
                line = line.strip()

                # Пропускаем строки с объяснениями
                if any(phrase in line.lower() for phrase in [
                    "вот перефразированный", "перефразированная версия",
                    "альтернативный вариант", "измененный текст"
                ]):
                    continue

                if line:
                    content_lines.append(line)

            return '\n'.join(content_lines)

        except Exception as e:
            logger.error(f"❌ Ошибка очистки ответа: {e}")
            return response

    def _get_cache_key(self, message_text: str, level: str) -> str:
        """Генерация ключа для кэша"""

        try:
            # Создаем хэш от текста сообщения и уровня
            content = f"{message_text}|{level}"
            return hashlib.md5(content.encode()).hexdigest()

        except Exception as e:
            logger.error(f"❌ Ошибка генерации ключа кэша: {e}")
            return f"{len(message_text)}_{level}"

    def _add_to_cache(self, cache_key: str, unique_message: str):
        """Добавление в кэш с контролем размера"""

        try:
            # Проверяем размер кэша
            if len(self.uniquification_cache) >= self.max_cache_size:
                # Удаляем 20% старых записей
                items_to_remove = self.max_cache_size // 5
                keys_to_remove = list(self.uniquification_cache.keys())[:items_to_remove]

                for key in keys_to_remove:
                    del self.uniquification_cache[key]

            self.uniquification_cache[cache_key] = unique_message

        except Exception as e:
            logger.error(f"❌ Ошибка добавления в кэш: {e}")

    async def generate_multiple_variants(
            self,
            message_text: str,
            count: int = 3,
            level: str = "medium"
    ) -> List[str]:
        """Генерация нескольких вариантов сообщения"""

        try:
            variants = []

            for i in range(count):
                # Добавляем небольшую вариацию в промпт для разнообразия
                variant_prompt = f"Вариант #{i + 1}. " if i > 0 else ""

                # Временно изменяем кэш ключ для каждого варианта
                temp_message = f"{variant_prompt}{message_text}"

                variant = await self.uniquify_message(temp_message, level)

                # Убираем добавленный префикс
                if variant.startswith(variant_prompt):
                    variant = variant[len(variant_prompt):]

                if variant and variant not in variants:
                    variants.append(variant)

            return variants

        except Exception as e:
            logger.error(f"❌ Ошибка генерации множественных вариантов: {e}")
            return [message_text]

    def get_cache_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""

        try:
            return {
                "cache_size": len(self.uniquification_cache),
                "max_cache_size": self.max_cache_size,
                "cache_usage_percent": (len(self.uniquification_cache) / self.max_cache_size) * 100
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики кэша: {e}")
            return {"cache_size": 0, "max_cache_size": 0, "cache_usage_percent": 0}

    def clear_cache(self):
        """Очистка кэша"""

        try:
            self.uniquification_cache.clear()
            logger.info("🧹 Кэш уникализации очищен")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша: {e}")

    async def test_uniquification(self, message_text: str) -> Dict[str, Any]:
        """Тестирование уникализации с примерами"""

        try:
            test_results = {
                "original": message_text,
                "variants": {},
                "success": True,
                "errors": []
            }

            # Тестируем разные уровни
            for level in ["light", "medium", "heavy"]:
                try:
                    variant = await self.uniquify_message(message_text, level)
                    test_results["variants"][level] = variant

                except Exception as e:
                    test_results["errors"].append(f"Ошибка уровня {level}: {str(e)}")
                    test_results["success"] = False

            return test_results

        except Exception as e:
            logger.error(f"❌ Ошибка тестирования уникализации: {e}")
            return {
                "original": message_text,
                "variants": {},
                "success": False,
                "errors": [str(e)]
            }

# Глобальный экземпляр ИИ уникализатора
ai_uniquifier = AIUniquifier()