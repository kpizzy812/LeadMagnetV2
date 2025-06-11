# cold_outreach/campaigns/campaign_manager.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload

from storage.database import get_db
from storage.models.cold_outreach import (
    OutreachCampaign, OutreachLead, OutreachLeadList,
    OutreachTemplate, OutreachMessage,
    CampaignSessionAssignment
)
from cold_outreach.templates.template_manager import TemplateManager
from cold_outreach.leads.lead_manager import LeadManager
from loguru import logger


class CampaignManager:
    """Менеджер кампаний холодной рассылки"""

    def __init__(self):
        self.template_manager = TemplateManager()
        self.lead_manager = LeadManager()

    async def initialize(self):
        """Инициализация менеджера кампаний"""
        try:
            await self.template_manager.initialize()
            await self.lead_manager.initialize()

            logger.info("✅ CampaignManager инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации CampaignManager: {e}")
            raise

    async def create_campaign(
            self,
            name: str,
            description: str,
            lead_list_id: int,
            template_id: int,
            session_names: List[str],
            settings: Dict[str, Any]
    ) -> Optional[int]:
        """Создание новой кампании"""

        try:
            async with get_db() as db:
                # Проверяем что список лидов и шаблон существуют
                lead_list = await db.get(OutreachLeadList, lead_list_id)
                template = await db.get(OutreachTemplate, template_id)

                if not lead_list:
                    logger.error(f"❌ Список лидов {lead_list_id} не найден")
                    return None

                if not template:
                    logger.error(f"❌ Шаблон {template_id} не найден")
                    return None

                # Создаем кампанию - ИСПРАВЛЕНИЕ: используем строковые статусы
                campaign = OutreachCampaign(
                    name=name,
                    description=description,
                    lead_list_id=lead_list_id,
                    template_id=template_id,
                    status="draft",  # ИСПРАВЛЕНИЕ: строка вместо enum
                    max_messages_per_day=settings.get("max_messages_per_day", 50),
                    delay_between_messages=settings.get("delay_between_messages", 1800),
                    use_premium_sessions_only=settings.get("use_premium_sessions_only", False),
                    enable_spambot_recovery=settings.get("enable_spambot_recovery", True),
                    daily_start_hour=settings.get("daily_start_hour", 10),
                    daily_end_hour=settings.get("daily_end_hour", 18)
                )

                db.add(campaign)
                await db.flush()
                await db.refresh(campaign)

                campaign_id = campaign.id

                # Создаем назначения сессий
                for session_name in session_names:
                    session_assignment = CampaignSessionAssignment(
                        campaign_id=campaign_id,
                        session_name=session_name,
                        daily_limit=settings.get("session_daily_limit", 10)
                    )
                    db.add(session_assignment)

                # Подсчитываем общее количество целей
                total_targets_result = await db.execute(
                    select(func.count(OutreachLead.id))
                    .where(
                        OutreachLead.lead_list_id == lead_list_id,
                        OutreachLead.is_processed == False,
                        OutreachLead.is_blocked == False
                    )
                )
                total_targets = total_targets_result.scalar() or 0

                campaign.total_targets = total_targets

                await db.commit()

                logger.info(f"✅ Создана кампания '{name}' с ID {campaign_id}")
                return campaign_id

        except Exception as e:
            logger.error(f"❌ Ошибка создания кампании '{name}': {e}")
            return None

    async def get_campaign(self, campaign_id: int) -> Optional[OutreachCampaign]:
        """Получение кампании по ID"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(OutreachCampaign)
                    .options(selectinload(OutreachCampaign.lead_list))
                    .options(selectinload(OutreachCampaign.template))
                    .options(selectinload(OutreachCampaign.session_assignments))
                    .where(OutreachCampaign.id == campaign_id)
                )
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"❌ Ошибка получения кампании {campaign_id}: {e}")
            return None

    async def validate_campaign(self, campaign: OutreachCampaign) -> Dict[str, Any]:
        """Валидация кампании перед запуском"""

        try:
            validation_result = {
                "valid": True,
                "errors": [],
                "warnings": []
            }

            # Проверяем статус
            if campaign.status != "draft":
                validation_result["errors"].append("Кампания должна быть в статусе 'draft'")

            # Проверяем наличие лидов
            if campaign.total_targets == 0:
                validation_result["errors"].append("Нет доступных лидов для рассылки")

            # Проверяем назначенные сессии
            if not campaign.session_assignments:
                validation_result["errors"].append("Не назначены сессии для кампании")

            # Проверяем шаблон
            if not campaign.template or not campaign.template.is_active:
                validation_result["errors"].append("Шаблон недоступен")

            # Проверяем список лидов
            if not campaign.lead_list or not campaign.lead_list.is_active:
                validation_result["errors"].append("Список лидов недоступен")

            # Предупреждения
            if campaign.max_messages_per_day > 100:
                validation_result["warnings"].append("Высокий лимит сообщений может привести к блокировкам")

            if len(campaign.session_assignments) == 1:
                validation_result["warnings"].append("Рекомендуется использовать несколько сессий")

            validation_result["valid"] = len(validation_result["errors"]) == 0

            return validation_result

        except Exception as e:
            logger.error(f"❌ Ошибка валидации кампании: {e}")
            return {
                "valid": False,
                "errors": [f"Ошибка валидации: {str(e)}"],
                "warnings": []
            }

    async def get_campaign_sessions(self, campaign_id: int) -> List[str]:
        """Получение списка сессий кампании"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(CampaignSessionAssignment.session_name)
                    .where(
                        CampaignSessionAssignment.campaign_id == campaign_id,
                        CampaignSessionAssignment.is_active == True
                    )
                )
                return [row[0] for row in result.fetchall()]

        except Exception as e:
            logger.error(f"❌ Ошибка получения сессий кампании {campaign_id}: {e}")
            return []

    async def get_next_leads_batch(self, campaign_id: int, batch_size: int = 10) -> List[Dict]:
        """Получение следующей порции лидов для обработки"""

        try:
            # Получаем лидов которые еще не обработаны
            leads = await self.lead_manager.get_leads_for_campaign(
                list_id=await self._get_campaign_list_id(campaign_id),
                limit=batch_size,
                only_unprocessed=True
            )

            return leads

        except Exception as e:
            logger.error(f"❌ Ошибка получения лидов для кампании {campaign_id}: {e}")
            return []

    async def generate_message_for_lead(self, campaign_id: int, lead_data: Dict) -> Optional[str]:
        """Генерация сообщения для лида"""

        try:
            campaign = await self.get_campaign(campaign_id)
            if not campaign:
                return None

            return await self.template_manager.generate_message_for_lead(
                template_id=campaign.template_id,
                lead_data=lead_data
            )

        except Exception as e:
            logger.error(f"❌ Ошибка генерации сообщения для кампании {campaign_id}: {e}")
            return None

    async def record_message_sent(
            self,
            campaign_id: int,
            lead_id: int,
            session_name: str,
            message_text: str
    ):
        """Запись отправленного сообщения"""

        try:
            async with get_db() as db:
                campaign = await self.get_campaign(campaign_id)
                if not campaign:
                    return

                # Создаем запись сообщения
                message = OutreachMessage(
                    campaign_id=campaign_id,
                    lead_id=lead_id,
                    template_id=campaign.template_id,
                    session_name=session_name,
                    message_text=message_text,
                    original_template_text=campaign.template.text,
                    status="sent",  # ИСПРАВЛЕНИЕ: строка вместо enum
                    sent_at=datetime.utcnow()
                )

                db.add(message)

                # Обновляем статистику кампании
                await db.execute(
                    update(OutreachCampaign)
                    .where(OutreachCampaign.id == campaign_id)
                    .values(
                        processed_targets=OutreachCampaign.processed_targets + 1,
                        successful_sends=OutreachCampaign.successful_sends + 1,
                        last_activity=datetime.utcnow()
                    )
                )

                # Помечаем лида как обработанного
                await self.lead_manager.mark_lead_processed(lead_id, success=True)

                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка записи отправленного сообщения: {e}")

    async def record_message_failed(self, campaign_id: int, lead_id: int, session_name: str):
        """Запись неудачной отправки"""

        try:
            async with get_db() as db:
                # Обновляем статистику кампании
                await db.execute(
                    update(OutreachCampaign)
                    .where(OutreachCampaign.id == campaign_id)
                    .values(
                        processed_targets=OutreachCampaign.processed_targets + 1,
                        failed_sends=OutreachCampaign.failed_sends + 1,
                        last_activity=datetime.utcnow()
                    )
                )

                # Помечаем лида как обработанного с ошибкой
                await self.lead_manager.mark_lead_processed(lead_id, success=False)

                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка записи неудачной отправки: {e}")

    async def update_campaign_status(self, campaign_id: int, status: str):
        """Обновление статуса кампании"""

        try:
            async with get_db() as db:
                await db.execute(
                    update(OutreachCampaign)
                    .where(OutreachCampaign.id == campaign_id)
                    .values(status=status)
                )
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса кампании {campaign_id}: {e}")

    async def finalize_campaign(self, campaign_id: int):
        """Финализация кампании"""

        try:
            async with get_db() as db:
                await db.execute(
                    update(OutreachCampaign)
                    .where(OutreachCampaign.id == campaign_id)
                    .values(
                        status="completed",  # ИСПРАВЛЕНИЕ: строка вместо enum
                        completed_at=datetime.utcnow()
                    )
                )
                await db.commit()

                logger.info(f"✅ Кампания {campaign_id} финализирована")

        except Exception as e:
            logger.error(f"❌ Ошибка финализации кампании {campaign_id}: {e}")

    async def get_campaign_progress(self, campaign_id: int) -> Dict[str, Any]:
        """Получение прогресса кампании"""

        try:
            campaign = await self.get_campaign(campaign_id)
            if not campaign:
                return {}

            progress_percent = 0
            if campaign.total_targets > 0:
                progress_percent = (campaign.processed_targets / campaign.total_targets) * 100

            return {
                "campaign_id": campaign_id,
                "name": campaign.name,
                "status": campaign.status,
                "total_targets": campaign.total_targets,
                "processed_targets": campaign.processed_targets,
                "successful_sends": campaign.successful_sends,
                "failed_sends": campaign.failed_sends,
                "progress_percent": round(progress_percent, 2),
                "started_at": campaign.started_at,
                "last_activity": campaign.last_activity
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения прогресса кампании {campaign_id}: {e}")
            return {}

    async def _get_campaign_list_id(self, campaign_id: int) -> Optional[int]:
        """Получение ID списка лидов кампании"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(OutreachCampaign.lead_list_id)
                    .where(OutreachCampaign.id == campaign_id)
                )
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"❌ Ошибка получения list_id кампании {campaign_id}: {e}")
            return None

    # НОВОЕ: Добавляем недостающий метод для получения шаблонов каналов
    async def get_channel_templates(self) -> List[OutreachTemplate]:
        """Получение шаблонов постов из каналов"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(OutreachTemplate)
                    .where(
                        OutreachTemplate.category == "channel_post",
                        OutreachTemplate.is_active == True
                    )
                    .order_by(OutreachTemplate.created_at.desc())
                )
                return result.scalars().all()

        except Exception as e:
            logger.error(f"❌ Ошибка получения шаблонов каналов: {e}")
            return []


# Глобальный экземпляр менеджера кампаний
campaign_manager = CampaignManager()