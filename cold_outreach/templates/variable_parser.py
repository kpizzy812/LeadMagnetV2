# cold_outreach/templates/variable_parser.py

import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger


class VariableParser:
    """Парсер переменных в шаблонах сообщений"""

    def __init__(self):
        # Паттерн для поиска переменных в формате {variable_name}
        self.variable_pattern = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')

        # Встроенные переменные и их описания
        self.built_in_variables = {
            "username": "Имя пользователя в Telegram (без @)",
            "first_name": "Имя пользователя",
            "last_name": "Фамилия пользователя",
            "full_name": "Полное имя (имя + фамилия)",
            "date": "Текущая дата в формате ДД.ММ.ГГГГ",
            "time": "Текущее время в формате ЧЧ:ММ",
            "day_name": "Название дня недели",
            "month_name": "Название месяца",
            "random_greeting": "Случайное приветствие",
            "random_emoji": "Случайный подходящий emoji"
        }

        # Случайные значения для вариативности
        self.random_greetings = [
            "Привет", "Здравствуй", "Добро пожаловать", "Доброго времени суток",
            "Хай", "Приветствую", "Добрый день", "Рад познакомиться"
        ]

        self.random_emojis = [
            "👋", "😊", "🚀", "💎", "⭐", "🔥", "💪", "🎯", "✨", "📈"
        ]

        self.day_names = {
            0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
            4: "пятница", 5: "суббота", 6: "воскресенье"
        }

        self.month_names = {
            1: "январь", 2: "февраль", 3: "март", 4: "апрель",
            5: "май", 6: "июнь", 7: "июль", 8: "август",
            9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
        }

    async def initialize(self):
        """Инициализация парсера"""
        logger.info("✅ VariableParser инициализирован")

    def extract_variables(self, text: str) -> List[str]:
        """Извлечение всех переменных из текста"""

        try:
            matches = self.variable_pattern.findall(text)
            # Удаляем дубликаты и сортируем
            variables = sorted(list(set(matches)))

            logger.debug(f"📝 Найдены переменные: {variables}")
            return variables

        except Exception as e:
            logger.error(f"❌ Ошибка извлечения переменных: {e}")
            return []

    async def substitute_variables(self, text: str, lead_data: Dict[str, Any]) -> str:
        """Подстановка значений переменных в текст"""

        try:
            result_text = text

            # Находим все переменные в тексте
            variables = self.extract_variables(text)

            for var in variables:
                placeholder = f"{{{var}}}"
                value = await self._get_variable_value(var, lead_data)

                if value is not None:
                    result_text = result_text.replace(placeholder, str(value))
                    logger.debug(f"🔄 Заменена переменная {var} на '{value}'")
                else:
                    logger.warning(f"⚠️ Не найдено значение для переменной {var}")
                    # Оставляем переменную как есть или заменяем на дефолтное значение
                    default_value = self._get_default_value(var)
                    if default_value:
                        result_text = result_text.replace(placeholder, default_value)

            return result_text

        except Exception as e:
            logger.error(f"❌ Ошибка подстановки переменных: {e}")
            return text  # Возвращаем оригинальный текст в случае ошибки

    async def _get_variable_value(self, variable_name: str, lead_data: Dict[str, Any]) -> Optional[str]:
        """Получение значения переменной"""

        try:
            # Проверяем данные лида
            if variable_name in lead_data and lead_data[variable_name]:
                return str(lead_data[variable_name])

            # Встроенные переменные
            if variable_name == "date":
                return datetime.now().strftime("%d.%m.%Y")

            elif variable_name == "time":
                return datetime.now().strftime("%H:%M")

            elif variable_name == "day_name":
                day_num = datetime.now().weekday()
                return self.day_names.get(day_num, "")

            elif variable_name == "month_name":
                month_num = datetime.now().month
                return self.month_names.get(month_num, "")

            elif variable_name == "random_greeting":
                import random
                return random.choice(self.random_greetings)

            elif variable_name == "random_emoji":
                import random
                return random.choice(self.random_emojis)

            elif variable_name == "full_name":
                # Составляем полное имя из имени и фамилии
                first_name = lead_data.get("first_name", "")
                last_name = lead_data.get("last_name", "")

                if first_name and last_name:
                    return f"{first_name} {last_name}"
                elif first_name:
                    return first_name
                elif last_name:
                    return last_name
                else:
                    return lead_data.get("username", "друг")

            # Дополнительные вычисляемые переменные
            elif variable_name == "greeting_with_name":
                greeting = await self._get_variable_value("random_greeting", lead_data)
                name = lead_data.get("first_name") or lead_data.get("username", "друг")
                return f"{greeting}, {name}"

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения значения переменной {variable_name}: {e}")
            return None

    def _get_default_value(self, variable_name: str) -> Optional[str]:
        """Получение значения по умолчанию для переменной"""

        defaults = {
            "username": "друг",
            "first_name": "друг",
            "last_name": "",
            "full_name": "друг",
            "random_greeting": "Привет",
            "random_emoji": "👋"
        }

        return defaults.get(variable_name)

    def validate_variables(self, text: str) -> Dict[str, Any]:
        """Валидация переменных в тексте"""

        try:
            variables = self.extract_variables(text)

            validation_result = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "variables": variables,
                "unknown_variables": [],
                "built_in_variables": []
            }

            for var in variables:
                if var in self.built_in_variables:
                    validation_result["built_in_variables"].append(var)
                elif var not in ["username", "first_name", "last_name", "full_name", "user_id"]:
                    validation_result["unknown_variables"].append(var)
                    validation_result["warnings"].append(
                        f"Неизвестная переменная '{var}' - убедитесь что она будет предоставлена"
                    )

            # Проверка на потенциальные проблемы
            if "username" not in variables and "first_name" not in variables:
                validation_result["warnings"].append(
                    "Рекомендуется добавить персонализацию с {username} или {first_name}"
                )

            return validation_result

        except Exception as e:
            logger.error(f"❌ Ошибка валидации переменных: {e}")
            return {
                "valid": False,
                "errors": [f"Ошибка валидации: {str(e)}"],
                "warnings": [],
                "variables": [],
                "unknown_variables": [],
                "built_in_variables": []
            }

    def get_available_variables(self) -> Dict[str, str]:
        """Получение списка доступных переменных"""

        return self.built_in_variables.copy()

    def preview_substitution(self, text: str, sample_data: Dict[str, Any] = None) -> str:
        """Предварительный просмотр с подстановкой тестовых данных"""

        try:
            if sample_data is None:
                sample_data = {
                    "username": "ivan_petrov",
                    "first_name": "Иван",
                    "last_name": "Петров",
                    "user_id": "123456789"
                }

            # Добавляем встроенные переменные
            import asyncio
            return asyncio.run(self.substitute_variables(text, sample_data))

        except Exception as e:
            logger.error(f"❌ Ошибка предварительного просмотра: {e}")
            return text

    def suggest_variables(self, text: str) -> List[str]:
        """Предложение переменных на основе содержимого текста"""

        try:
            suggestions = []
            text_lower = text.lower()

            # Анализируем текст и предлагаем подходящие переменные
            if any(word in text_lower for word in ["имя", "зовут", "называть"]):
                suggestions.append("first_name")

            if any(word in text_lower for word in ["привет", "здравствуй", "добро пожаловать"]):
                suggestions.append("random_greeting")

            if any(word in text_lower for word in ["сегодня", "день", "дата"]):
                suggestions.append("date")

            if any(word in text_lower for word in ["время", "сейчас"]):
                suggestions.append("time")

            if "друг" in text_lower or "товарищ" in text_lower:
                suggestions.append("username")

            return list(set(suggestions))  # Убираем дубликаты

        except Exception as e:
            logger.error(f"❌ Ошибка предложения переменных: {e}")
            return []

    def analyze_template_complexity(self, text: str) -> Dict[str, Any]:
        """Анализ сложности шаблона"""

        try:
            variables = self.extract_variables(text)

            analysis = {
                "total_variables": len(variables),
                "unique_variables": len(set(variables)),
                "personalization_level": "none",
                "complexity_score": 0,
                "recommendations": []
            }

            # Определяем уровень персонализации
            if any(var in variables for var in ["username", "first_name", "full_name"]):
                analysis["personalization_level"] = "basic"
                analysis["complexity_score"] += 1

            if any(var in variables for var in ["last_name", "random_greeting"]):
                analysis["personalization_level"] = "advanced"
                analysis["complexity_score"] += 1

            if any(var in variables for var in ["date", "time", "day_name"]):
                analysis["personalization_level"] = "dynamic"
                analysis["complexity_score"] += 1

            # Добавляем рекомендации
            if analysis["total_variables"] == 0:
                analysis["recommendations"].append(
                    "Добавьте хотя бы одну переменную для персонализации"
                )

            if analysis["total_variables"] > 5:
                analysis["recommendations"].append(
                    "Слишком много переменных может усложнить сообщение"
                )

            return analysis

        except Exception as e:
            logger.error(f"❌ Ошибка анализа сложности шаблона: {e}")
            return {
                "total_variables": 0,
                "unique_variables": 0,
                "personalization_level": "none",
                "complexity_score": 0,
                "recommendations": []
            }

variable_parser = VariableParser()