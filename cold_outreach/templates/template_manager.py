# cold_outreach/templates/template_manager.py

import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.cold_outreach import OutreachTemplate, OutreachLead
from cold_outreach.templates.variable_parser import VariableParser
from cold_outreach.templates.ai_uniquifier import AIUniquifier
from loguru import logger


class TemplateManager:
    """Менеджер шаблонов сообщений для холодной рассылки"""

    def __init__(self):
        self.variable_parser = VariableParser()
        self.ai_uniquifier = AIUniquifier()
        self.templates_cache: Dict[int, OutreachTemplate] = {}

    async def initialize(self):
        """Инициализация менеджера шаблонов"""
        try:
            await self.variable_parser.initialize()
            await self.ai_uniquifier.initialize()
            await self._load_templates_cache()

            logger.info("✅ TemplateManager инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации TemplateManager: {e}")
            raise

    async def _load_templates_cache(self):
        """Загрузка активных шаблонов в кэш"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(OutreachTemplate).where(OutreachTemplate.is_active == True)
                )
                templates = result.scalars().all()

                for template in templates:
                    self.templates_cache[template.id] = template

                logger.info(f"📋 Загружено {len(self.templates_cache)} шаблонов в кэш")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки кэша шаблонов: {e}")

    async def create_template(
            self,
            name: str,
            text: str,
            description: str = None,
            persona_type: str = None,
            category: str = None,
            enable_ai_uniquification: bool = False,
            uniquification_level: str = "medium",
            created_by: str = None
    ) -> Optional[int]:
        """Создание нового шаблона"""

        try:
            # Извлекаем переменные из текста
            variables = self.variable_parser.extract_variables(text)

            async with get_db() as db:
                template = OutreachTemplate(
                    name=name,
                    description=description,
                    text=text,
                    variables=variables,
                    persona_type=persona_type,
                    category=category,
                    enable_ai_uniquification=enable_ai_uniquification,
                    uniquification_level=uniquification_level,
                    created_by=created_by
                )

                db.add(template)
                await db.flush()
                await db.refresh(template)

                template_id = template.id

                # Добавляем в кэш
                self.templates_cache[template_id] = template

                await db.commit()

                logger.info(f"✅ Создан шаблон '{name}' с ID {template_id}")
                return template_id

        except Exception as e:
            logger.error(f"❌ Ошибка создания шаблона '{name}': {e}")
            return None

    async def get_template(self, template_id: int) -> Optional[OutreachTemplate]:
        """Получение шаблона по ID"""

        try:
            # Сначала проверяем кэш
            if template_id in self.templates_cache:
                return self.templates_cache[template_id]

            # Если нет в кэше, загружаем из БД
            async with get_db() as db:
                template = await db.get(OutreachTemplate, template_id)

                if template and template.is_active:
                    self.templates_cache[template_id] = template
                    return template

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения шаблона {template_id}: {e}")
            return None

    async def generate_message_for_lead(
            self,
            template_id: int,
            lead_data: Dict[str, Any]
    ) -> Optional[str]:
        """Генерация сообщения для лида на основе шаблона"""

        try:
            template = await self.get_template(template_id)
            if not template:
                logger.error(f"❌ Шаблон {template_id} не найден")
                return None

            # Подставляем переменные
            message_text = await self.variable_parser.substitute_variables(
                template.text, lead_data
            )

            # Применяем ИИ уникализацию если включена
            if template.enable_ai_uniquification:
                message_text = await self.ai_uniquifier.uniquify_message(
                    message_text,
                    template.uniquification_level,
                    lead_data
                )

            # Обновляем статистику использования
            await self._update_template_usage(template_id)

            return message_text

        except Exception as e:
            logger.error(f"❌ Ошибка генерации сообщения по шаблону {template_id}: {e}")
            return None

    async def _update_template_usage(self, template_id: int):
        """Обновление статистики использования шаблона"""

        try:
            async with get_db() as db:
                await db.execute(
                    update(OutreachTemplate)
                    .where(OutreachTemplate.id == template_id)
                    .values(usage_count=OutreachTemplate.usage_count + 1)
                )
                await db.commit()

                # Обновляем кэш
                if template_id in self.templates_cache:
                    self.templates_cache[template_id].usage_count += 1

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики шаблона {template_id}: {e}")

    async def get_templates_by_category(self, category: str) -> List[OutreachTemplate]:
        """Получение шаблонов по категории"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(OutreachTemplate)
                    .where(
                        OutreachTemplate.category == category,
                        OutreachTemplate.is_active == True
                    )
                    .order_by(OutreachTemplate.usage_count.desc())
                )
                return result.scalars().all()

        except Exception as e:
            logger.error(f"❌ Ошибка получения шаблонов категории '{category}': {e}")
            return []

    async def get_templates_by_persona(self, persona_type: str) -> List[OutreachTemplate]:
        """Получение шаблонов по типу персоны"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(OutreachTemplate)
                    .where(
                        OutreachTemplate.persona_type == persona_type,
                        OutreachTemplate.is_active == True
                    )
                    .order_by(OutreachTemplate.conversion_rate.desc())
                )
                return result.scalars().all()

        except Exception as e:
            logger.error(f"❌ Ошибка получения шаблонов персоны '{persona_type}': {e}")
            return []

    async def update_template(
            self,
            template_id: int,
            **updates
    ) -> bool:
        """Обновление шаблона"""

        try:
            # Если обновляется текст, пересчитываем переменные
            if 'text' in updates:
                updates['variables'] = self.variable_parser.extract_variables(updates['text'])

            async with get_db() as db:
                await db.execute(
                    update(OutreachTemplate)
                    .where(OutreachTemplate.id == template_id)
                    .values(**updates)
                )
                await db.commit()

                # Обновляем кэш
                if template_id in self.templates_cache:
                    for key, value in updates.items():
                        setattr(self.templates_cache[template_id], key, value)

                logger.info(f"✅ Шаблон {template_id} обновлен")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка обновления шаблона {template_id}: {e}")
            return False

    async def delete_template(self, template_id: int) -> bool:
        """Мягкое удаление шаблона (деактивация)"""

        try:
            await self.update_template(template_id, is_active=False)

            # Удаляем из кэша
            if template_id in self.templates_cache:
                del self.templates_cache[template_id]

            logger.info(f"🗑️ Шаблон {template_id} деактивирован")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка удаления шаблона {template_id}: {e}")
            return False

    async def get_template_stats(self, template_id: int) -> Dict[str, Any]:
        """Получение статистики шаблона"""

        try:
            async with get_db() as db:
                template = await db.get(OutreachTemplate, template_id)
                if not template:
                    return {}

                # Дополнительная статистика из сообщений
                from storage.models.cold_outreach import OutreachMessage, OutreachMessageStatus

                total_sent_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(OutreachMessage.template_id == template_id)
                )
                total_sent = total_sent_result.scalar() or 0

                successful_sent_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(
                        OutreachMessage.template_id == template_id,
                        OutreachMessage.status == OutreachMessageStatus.SENT
                    )
                )
                successful_sent = successful_sent_result.scalar() or 0

                responses_result = await db.execute(
                    select(func.count(OutreachMessage.id))
                    .where(
                        OutreachMessage.template_id == template_id,
                        OutreachMessage.got_response == True
                    )
                )
                responses = responses_result.scalar() or 0

                return {
                    "template_id": template_id,
                    "name": template.name,
                    "usage_count": template.usage_count,
                    "total_sent": total_sent,
                    "successful_sent": successful_sent,
                    "delivery_rate": (successful_sent / max(total_sent, 1)) * 100,
                    "response_count": responses,
                    "response_rate": (responses / max(successful_sent, 1)) * 100,
                    "conversion_rate": template.conversion_rate,
                    "avg_response_time": template.avg_response_time,
                    "created_at": template.created_at,
                    "last_used": template.updated_at
                }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики шаблона {template_id}: {e}")
            return {}

    async def get_best_template_for_persona(self, persona_type: str) -> Optional[OutreachTemplate]:
        """Получение лучшего шаблона для персоны (по конверсии)"""

        try:
            templates = await self.get_templates_by_persona(persona_type)

            if not templates:
                # Если нет шаблонов для конкретной персоны, берем общие
                async with get_db() as db:
                    result = await db.execute(
                        select(OutreachTemplate)
                        .where(
                            OutreachTemplate.persona_type.is_(None),
                            OutreachTemplate.is_active == True
                        )
                        .order_by(OutreachTemplate.conversion_rate.desc())
                        .limit(1)
                    )
                    return result.scalar_one_or_none()

            return templates[0] if templates else None

        except Exception as e:
            logger.error(f"❌ Ошибка получения лучшего шаблона для {persona_type}: {e}")
            return None

    async def validate_template(self, text: str) -> Dict[str, Any]:
        """Валидация шаблона сообщения"""

        try:
            validation_result = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "variables": [],
                "length": len(text),
                "estimated_length_after_substitution": 0
            }

            # Проверка длины
            if len(text) < 10:
                validation_result["errors"].append("Слишком короткий текст (менее 10 символов)")
                validation_result["valid"] = False

            if len(text) > 4000:
                validation_result["errors"].append("Слишком длинный текст (более 4000 символов)")
                validation_result["valid"] = False

            # Извлечение и валидация переменных
            variables = self.variable_parser.extract_variables(text)
            validation_result["variables"] = variables

            # Проверка на подозрительные слова
            suspicious_words = ["спам", "реклама", "скидка", "акция", "купить", "продажа"]
            text_lower = text.lower()

            found_suspicious = [word for word in suspicious_words if word in text_lower]
            if found_suspicious:
                validation_result["warnings"].append(
                    f"Найдены подозрительные слова: {', '.join(found_suspicious)}"
                )

            # Оценка длины после подстановки переменных
            estimated_length = len(text)
            for var in variables:
                if var == "username":
                    estimated_length += 15  # Средняя длина username
                elif var in ["first_name", "last_name"]:
                    estimated_length += 10
                elif var == "full_name":
                    estimated_length += 20
                else:
                    estimated_length += 5

            validation_result["estimated_length_after_substitution"] = estimated_length

            if estimated_length > 4096:
                validation_result["warnings"].append(
                    "Сообщение может превысить лимит Telegram после подстановки переменных"
                )

            return validation_result

        except Exception as e:
            logger.error(f"❌ Ошибка валидации шаблона: {e}")
            return {
                "valid": False,
                "errors": [f"Ошибка валидации: {str(e)}"],
                "warnings": [],
                "variables": [],
                "length": 0,
                "estimated_length_after_substitution": 0
            }

    async def duplicate_template(self, template_id: int, new_name: str) -> Optional[int]:
        """Дублирование шаблона"""

        try:
            original = await self.get_template(template_id)
            if not original:
                return None

            return await self.create_template(
                name=new_name,
                text=original.text,
                description=f"Копия шаблона '{original.name}'",
                persona_type=original.persona_type,
                category=original.category,
                enable_ai_uniquification=original.enable_ai_uniquification,
                uniquification_level=original.uniquification_level
            )

        except Exception as e:
            logger.error(f"❌ Ошибка дублирования шаблона {template_id}: {e}")
            return None

    async def get_templates_list(
            self,
            limit: int = 50,
            offset: int = 0,
            category: str = None,
            persona_type: str = None,
            active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Получение списка шаблонов с фильтрацией"""

        try:
            async with get_db() as db:
                query = select(OutreachTemplate)

                # Применяем фильтры
                if active_only:
                    query = query.where(OutreachTemplate.is_active == True)

                if category:
                    query = query.where(OutreachTemplate.category == category)

                if persona_type:
                    query = query.where(OutreachTemplate.persona_type == persona_type)

                # Сортировка и лимиты
                query = query.order_by(OutreachTemplate.created_at.desc())
                query = query.offset(offset).limit(limit)

                result = await db.execute(query)
                templates = result.scalars().all()

                return [
                    {
                        "id": t.id,
                        "name": t.name,
                        "description": t.description,
                        "category": t.category,
                        "persona_type": t.persona_type,
                        "usage_count": t.usage_count,
                        "conversion_rate": t.conversion_rate,
                        "created_at": t.created_at,
                        "is_active": t.is_active,
                        "variables_count": len(t.variables) if t.variables else 0
                    }
                    for t in templates
                ]

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка шаблонов: {e}")
            return []

    async def refresh_cache(self):
        """Принудительное обновление кэша шаблонов"""

        try:
            self.templates_cache.clear()
            await self._load_templates_cache()
            logger.info("🔄 Кэш шаблонов обновлен")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления кэша шаблонов: {e}")

    async def get_template_variables_usage(self) -> Dict[str, int]:
        """Статистика использования переменных в шаблонах"""

        try:
            variables_count = {}

            for template in self.templates_cache.values():
                if template.variables:
                    for var in template.variables:
                        variables_count[var] = variables_count.get(var, 0) + 1

            return dict(sorted(variables_count.items(), key=lambda x: x[1], reverse=True))

        except Exception as e:
            logger.error(f"❌ Ошибка подсчета использования переменных: {e}")
            return {}

    async def suggest_improvements(self, template_id: int) -> List[str]:
        """Предложения по улучшению шаблона"""

        try:
            template = await self.get_template(template_id)
            if not template:
                return []

            suggestions = []
            text = template.text.lower()

            # Анализируем текст
            if len(template.text) < 50:
                suggestions.append("Увеличьте длину сообщения для большей информативности")

            if len(template.text) > 500:
                suggestions.append("Сократите сообщение для лучшей читаемости")

            if not template.variables:
                suggestions.append("Добавьте персонализацию с помощью переменных {username} или {first_name}")

            if template.conversion_rate < 0.05:  # Менее 5%
                suggestions.append("Низкая конверсия - попробуйте другой подход или стиль")

            if "криптовалют" in text and "риск" not in text:
                suggestions.append("Добавьте упоминание рисков для соответствия требованиям")

            if not any(word in text for word in ["привет", "здравствуй", "добро пожаловать"]):
                suggestions.append("Добавьте приветствие для более дружелюбного тона")

            return suggestions

        except Exception as e:
            logger.error(f"❌ Ошибка генерации предложений для шаблона {template_id}: {e}")
            return []

template_manager = TemplateManager()