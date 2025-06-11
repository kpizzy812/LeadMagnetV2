# cold_outreach/leads/lead_manager.py

import re
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.cold_outreach import OutreachLeadList, OutreachLead
from cold_outreach.leads.duplicate_filter import DuplicateFilter
from loguru import logger


class LeadManager:
    """Менеджер лидов для холодной рассылки"""

    def __init__(self):
        self.duplicate_filter = DuplicateFilter()

    async def initialize(self):
        """Инициализация менеджера лидов"""
        try:
            await self.duplicate_filter.initialize()
            logger.info("✅ LeadManager инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации LeadManager: {e}")
            raise

    async def create_lead_list(
            self,
            name: str,
            description: str = None,
            source: str = None,
            tags: List[str] = None
    ) -> Optional[int]:
        """Создание нового списка лидов"""

        try:
            async with get_db() as db:
                lead_list = OutreachLeadList(
                    name=name,
                    description=description,
                    source=source,
                    tags=tags or []
                )

                db.add(lead_list)
                await db.flush()
                await db.refresh(lead_list)

                list_id = lead_list.id
                await db.commit()

                logger.info(f"✅ Создан список лидов '{name}' с ID {list_id}")
                return list_id

        except Exception as e:
            logger.error(f"❌ Ошибка создания списка лидов '{name}': {e}")
            return None

    async def add_leads_to_list(
            self,
            list_id: int,
            leads_data: List[Dict[str, Any]],
            skip_duplicates: bool = True
    ) -> Dict[str, Any]:
        """Добавление лидов в список"""

        try:
            result = {
                "total_processed": len(leads_data),
                "added": 0,
                "skipped": 0,
                "errors": 0,
                "duplicates": 0,
                "invalid": 0,
                "details": []
            }

            async with get_db() as db:
                # Проверяем что список существует
                lead_list = await db.get(OutreachLeadList, list_id)
                if not lead_list:
                    logger.error(f"❌ Список лидов {list_id} не найден")
                    return result

                for lead_data in leads_data:
                    try:
                        # Валидируем данные лида
                        validation_result = self._validate_lead_data(lead_data)
                        if not validation_result["valid"]:
                            result["invalid"] += 1
                            result["details"].append({
                                "username": lead_data.get("username", "unknown"),
                                "status": "invalid",
                                "reason": validation_result["error"]
                            })
                            continue

                        username = self._normalize_username(lead_data["username"])

                        # Проверяем дубликаты если нужно
                        if skip_duplicates:
                            is_duplicate = await self.duplicate_filter.is_duplicate(
                                username, list_id
                            )
                            if is_duplicate:
                                result["duplicates"] += 1
                                result["details"].append({
                                    "username": username,
                                    "status": "duplicate",
                                    "reason": "Уже существует в списке"
                                })
                                continue

                        # Создаем лида
                        lead = OutreachLead(
                            lead_list_id=list_id,
                            username=username,
                            first_name=lead_data.get("first_name"),
                            last_name=lead_data.get("last_name"),
                            full_name=self._build_full_name(
                                lead_data.get("first_name"),
                                lead_data.get("last_name")
                            ),
                            user_id=lead_data.get("user_id"),
                            is_premium=lead_data.get("is_premium")
                        )

                        db.add(lead)
                        result["added"] += 1

                        # Добавляем в фильтр дубликатов
                        await self.duplicate_filter.add_username(username, list_id)

                        result["details"].append({
                            "username": username,
                            "status": "added",
                            "reason": "Успешно добавлен"
                        })

                    except Exception as e:
                        result["errors"] += 1
                        result["details"].append({
                            "username": lead_data.get("username", "unknown"),
                            "status": "error",
                            "reason": str(e)
                        })
                        logger.error(f"❌ Ошибка добавления лида {lead_data}: {e}")

                # Обновляем статистику списка
                await db.execute(
                    update(OutreachLeadList)
                    .where(OutreachLeadList.id == list_id)
                    .values(total_leads=OutreachLeadList.total_leads + result["added"])
                )

                await db.commit()

                logger.info(
                    f"📊 Обработано лидов для списка {list_id}: "
                    f"добавлено {result['added']}, пропущено {result['skipped']}, "
                    f"дубликатов {result['duplicates']}, ошибок {result['errors']}"
                )

                return result

        except Exception as e:
            logger.error(f"❌ Ошибка добавления лидов в список {list_id}: {e}")
            return result

    def _validate_lead_data(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация данных лида"""

        try:
            if not isinstance(lead_data, dict):
                return {"valid": False, "error": "Данные лида должны быть словарем"}

            if "username" not in lead_data:
                return {"valid": False, "error": "Отсутствует username"}

            username = str(lead_data["username"]).strip()
            if not username:
                return {"valid": False, "error": "Пустой username"}

            # Проверяем формат username
            if not self._is_valid_username(username):
                return {"valid": False, "error": "Некорректный формат username"}

            return {"valid": True, "error": None}

        except Exception as e:
            return {"valid": False, "error": f"Ошибка валидации: {str(e)}"}

    def _is_valid_username(self, username: str) -> bool:
        """Проверка корректности username"""

        try:
            # Убираем @ если есть
            clean_username = username.lstrip("@")

            # Проверяем длину (5-32 символа для Telegram)
            if len(clean_username) < 5 or len(clean_username) > 32:
                return False

            # Не должен содержать двойные _
            if '__' in clean_username:
                return False

            return True

        except Exception:
            return False

    def _normalize_username(self, username: str) -> str:
        """Нормализация username"""

        try:
            # Убираем @ и лишние пробелы
            normalized = str(username).strip().lstrip("@")
            return normalized.lower()

        except Exception:
            return username

    def _build_full_name(self, first_name: str, last_name: str) -> Optional[str]:
        """Построение полного имени"""

        try:
            parts = []

            if first_name and first_name.strip():
                parts.append(first_name.strip())

            if last_name and last_name.strip():
                parts.append(last_name.strip())

            return " ".join(parts) if parts else None

        except Exception:
            return None

    async def import_leads_from_text(
            self,
            list_id: int,
            text: str,
            format_type: str = "username_only"
    ) -> Dict[str, Any]:
        """Импорт лидов из текста"""

        try:
            leads_data = []

            if format_type == "username_only":
                leads_data = self._parse_username_list(text)
            elif format_type == "csv":
                leads_data = self._parse_csv_format(text)
            elif format_type == "json":
                leads_data = self._parse_json_format(text)
            else:
                return {
                    "total_processed": 0,
                    "added": 0,
                    "errors": 1,
                    "details": [{"error": f"Неподдерживаемый формат: {format_type}"}]
                }

            if not leads_data:
                return {
                    "total_processed": 0,
                    "added": 0,
                    "errors": 1,
                    "details": [{"error": "Не удалось извлечь лидов из текста"}]
                }

            return await self.add_leads_to_list(list_id, leads_data)

        except Exception as e:
            logger.error(f"❌ Ошибка импорта лидов из текста: {e}")
            return {
                "total_processed": 0,
                "added": 0,
                "errors": 1,
                "details": [{"error": str(e)}]
            }

    def _parse_username_list(self, text: str) -> List[Dict[str, Any]]:
        """Парсинг списка username'ов"""

        try:
            # Разделяем по строкам и очищаем
            lines = [line.strip() for line in text.split('\n') if line.strip()]

            leads = []
            for line in lines:
                # Может быть несколько username в одной строке
                usernames = re.findall(r'@?([a-zA-Z0-9_]{5,32})', line)

                for username in usernames:
                    if self._is_valid_username(username):
                        leads.append({"username": username})

            return leads

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга списка username: {e}")
            return []

    def _parse_csv_format(self, text: str) -> List[Dict[str, Any]]:
        """Парсинг CSV формата"""

        try:
            import csv
            from io import StringIO

            leads = []
            csv_reader = csv.DictReader(StringIO(text))

            for row in csv_reader:
                lead_data = {}

                # Ищем username в разных колонках
                for key, value in row.items():
                    key_lower = key.lower()
                    if 'username' in key_lower or 'user' in key_lower:
                        lead_data['username'] = value
                    elif 'first' in key_lower or 'name' in key_lower:
                        lead_data['first_name'] = value
                    elif 'last' in key_lower or 'surname' in key_lower:
                        lead_data['last_name'] = value
                    elif 'id' in key_lower:
                        lead_data['user_id'] = value

                if 'username' in lead_data:
                    leads.append(lead_data)

            return leads

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга CSV: {e}")
            return []

    def _parse_json_format(self, text: str) -> List[Dict[str, Any]]:
        """Парсинг JSON формата"""

        try:
            import json
            data = json.loads(text)

            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'leads' in data:
                return data['leads']
            else:
                return []

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            return []

    async def get_leads_for_campaign(
            self,
            list_id: int,
            limit: int = 100,
            offset: int = 0,
            only_unprocessed: bool = True
    ) -> List[Dict[str, Any]]:
        """Получение лидов для кампании"""

        try:
            async with get_db() as db:
                query = select(OutreachLead).where(OutreachLead.lead_list_id == list_id)

                if only_unprocessed:
                    query = query.where(OutreachLead.is_processed == False)

                # Исключаем заблокированных
                query = query.where(OutreachLead.is_blocked == False)

                query = query.order_by(OutreachLead.created_at).offset(offset).limit(limit)

                result = await db.execute(query)
                leads = result.scalars().all()

                return [
                    {
                        "id": lead.id,
                        "username": lead.username,
                        "first_name": lead.first_name,
                        "last_name": lead.last_name,
                        "full_name": lead.full_name,
                        "user_id": lead.user_id,
                        "is_premium": lead.is_premium
                    }
                    for lead in leads
                ]

        except Exception as e:
            logger.error(f"❌ Ошибка получения лидов для кампании: {e}")
            return []

    async def mark_lead_processed(self, lead_id: int, success: bool = True):
        """Отметка лида как обработанного"""

        try:
            async with get_db() as db:
                updates = {
                    "is_processed": True,
                    "last_contact_attempt": datetime.utcnow()
                }

                if success:
                    updates["successful_contacts"] = OutreachLead.successful_contacts + 1
                else:
                    updates["failed_contacts"] = OutreachLead.failed_contacts + 1

                await db.execute(
                    update(OutreachLead)
                    .where(OutreachLead.id == lead_id)
                    .values(**updates)
                )
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка отметки лида {lead_id} как обработанного: {e}")

    async def mark_lead_blocked(self, lead_id: int, reason: str):
        """Блокировка лида"""

        try:
            async with get_db() as db:
                await db.execute(
                    update(OutreachLead)
                    .where(OutreachLead.id == lead_id)
                    .values(
                        is_blocked=True,
                        block_reason=reason,
                        last_error=reason
                    )
                )
                await db.commit()

                logger.info(f"🚫 Лид {lead_id} заблокирован: {reason}")

        except Exception as e:
            logger.error(f"❌ Ошибка блокировки лида {lead_id}: {e}")

    async def get_list_stats(self, list_id: int) -> Dict[str, Any]:
        """Получение статистики списка лидов"""

        try:
            async with get_db() as db:
                # Базовая информация о списке
                lead_list = await db.get(OutreachLeadList, list_id)
                if not lead_list:
                    return {}

                # Статистика лидов
                total_result = await db.execute(
                    select(func.count(OutreachLead.id))
                    .where(OutreachLead.lead_list_id == list_id)
                )
                total_leads = total_result.scalar() or 0

                processed_result = await db.execute(
                    select(func.count(OutreachLead.id))
                    .where(
                        OutreachLead.lead_list_id == list_id,
                        OutreachLead.is_processed == True
                    )
                )
                processed_leads = processed_result.scalar() or 0

                blocked_result = await db.execute(
                    select(func.count(OutreachLead.id))
                    .where(
                        OutreachLead.lead_list_id == list_id,
                        OutreachLead.is_blocked == True
                    )
                )
                blocked_leads = blocked_result.scalar() or 0

                successful_result = await db.execute(
                    select(func.sum(OutreachLead.successful_contacts))
                    .where(OutreachLead.lead_list_id == list_id)
                )
                successful_contacts = successful_result.scalar() or 0

                failed_result = await db.execute(
                    select(func.sum(OutreachLead.failed_contacts))
                    .where(OutreachLead.lead_list_id == list_id)
                )
                failed_contacts = failed_result.scalar() or 0

                return {
                    "list_id": list_id,
                    "name": lead_list.name,
                    "description": lead_list.description,
                    "source": lead_list.source,
                    "tags": lead_list.tags,
                    "total_leads": total_leads,
                    "processed_leads": processed_leads,
                    "unprocessed_leads": total_leads - processed_leads,
                    "blocked_leads": blocked_leads,
                    "available_leads": total_leads - processed_leads - blocked_leads,
                    "successful_contacts": successful_contacts,
                    "failed_contacts": failed_contacts,
                    "success_rate": (successful_contacts / max(successful_contacts + failed_contacts, 1)) * 100,
                    "created_at": lead_list.created_at,
                    "is_active": lead_list.is_active
                }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики списка {list_id}: {e}")
            return {}

    async def delete_lead_list(self, list_id: int) -> bool:
        """Удаление списка лидов"""

        try:
            async with get_db() as db:
                # Помечаем как неактивный вместо удаления
                await db.execute(
                    update(OutreachLeadList)
                    .where(OutreachLeadList.id == list_id)
                    .values(is_active=False)
                )
                await db.commit()

                logger.info(f"🗑️ Список лидов {list_id} деактивирован")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка удаления списка лидов {list_id}: {e}")
            return False

    async def get_all_lists(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Получение всех списков лидов"""

        try:
            async with get_db() as db:
                query = select(OutreachLeadList)

                if active_only:
                    query = query.where(OutreachLeadList.is_active == True)

                query = query.order_by(OutreachLeadList.created_at.desc())

                result = await db.execute(query)
                lists = result.scalars().all()

                return [
                    {
                        "id": lst.id,
                        "name": lst.name,
                        "description": lst.description,
                        "source": lst.source,
                        "tags": lst.tags,
                        "total_leads": lst.total_leads,
                        "processed_leads": lst.processed_leads,
                        "successful_sends": lst.successful_sends,
                        "failed_sends": lst.failed_sends,
                        "created_at": lst.created_at,
                        "is_active": lst.is_active
                    }
                    for lst in lists
                ]

        except Exception as e:
            logger.error(f"❌ Ошибка получения списков лидов: {e}")
            return []

    async def clean_invalid_leads(self, list_id: int) -> Dict[str, int]:
        """Очистка невалидных лидов из списка"""

        try:
            async with get_db() as db:
                # Получаем всех лидов списка
                result = await db.execute(
                    select(OutreachLead).where(OutreachLead.lead_list_id == list_id)
                )
                leads = result.scalars().all()

                cleaned = 0
                for lead in leads:
                    if not self._is_valid_username(lead.username):
                        await db.execute(
                            update(OutreachLead)
                            .where(OutreachLead.id == lead.id)
                            .values(
                                is_blocked=True,
                                block_reason="invalid_username"
                            )
                        )
                        cleaned += 1

                await db.commit()

                logger.info(f"🧹 Очищено {cleaned} невалидных лидов из списка {list_id}")

                return {
                    "cleaned": cleaned,
                    "total_checked": len(leads)
                }

        except Exception as e:
            logger.error(f"❌ Ошибка очистки невалидных лидов: {e}")
            return {"cleaned": 0, "total_checked": 0}