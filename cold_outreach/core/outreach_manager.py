# cold_outreach/core/outreach_manager.py

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy import select, func

from storage.database import get_db
from storage.models.cold_outreach import OutreachCampaign, CampaignStatus
from storage.models.base import Session, SessionStatus
from cold_outreach.core.session_controller import SessionController
from cold_outreach.safety.rate_limiter import RateLimiter
from cold_outreach.safety.error_handler import OutreachErrorHandler
from cold_outreach.campaigns.campaign_manager import campaign_manager
from loguru import logger
from cold_outreach.core.message_sender import message_sender


class OutreachManager:
    """Центральный менеджер системы холодной рассылки"""

    def __init__(self):
        self.session_controller = SessionController()
        self.rate_limiter = RateLimiter()
        self.error_handler = OutreachErrorHandler()
        self.is_running = False

    async def initialize(self):
        """Инициализация менеджера"""
        try:
            await self.session_controller.initialize()
            await self.rate_limiter.initialize()

            logger.info("✅ OutreachManager инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации OutreachManager: {e}")
            raise

    async def start_campaign(self, campaign_id: int) -> bool:
        """Запуск кампании рассылки"""

        try:

            campaign = await campaign_manager.get_campaign(campaign_id)
            if not campaign:
                logger.error(f"❌ Кампания {campaign_id} не найдена")
                return False

            # Валидация кампании
            validation = await campaign_manager.validate_campaign(campaign)
            if not validation["valid"]:
                logger.error(f"❌ Кампания {campaign_id} не прошла валидацию: {validation['errors']}")
                return False

            # Переключаем сессии в режим рассылки
            session_names = await campaign_manager.get_campaign_sessions(campaign_id)

            for session_name in session_names:
                await self.session_controller.switch_to_outreach_mode(session_name)

            # Обновляем статус кампании
            await campaign_manager.update_campaign_status(campaign_id, CampaignStatus.ACTIVE.value)

            # Запускаем обработку кампании
            asyncio.create_task(self._process_campaign(campaign_id))

            logger.info(f"🚀 Кампания {campaign_id} запущена")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка запуска кампании {campaign_id}: {e}")
            return False

    async def stop_campaign(self, campaign_id: int) -> bool:
        """Остановка кампании"""
        try:
            from cold_outreach.campaigns.campaign_manager import campaign_manager

            # Получаем сессии кампании
            session_names = await campaign_manager.get_campaign_sessions(campaign_id)

            # Возвращаем сессии в режим ответов С сканированием пропущенных
            for session_name in session_names:
                await self.session_controller.switch_to_response_mode(session_name, scan_missed=True)

            # Обновляем статус
            await campaign_manager.update_campaign_status(campaign_id, CampaignStatus.PAUSED)

            logger.info(f"⏸️ Кампания {campaign_id} остановлена, сессии переведены в режим ответов")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка остановки кампании {campaign_id}: {e}")
            return False

    async def _process_campaign(self, campaign_id: int):
        """Обработка кампании в фоне"""
        try:
            while True:
                # Проверяем статус кампании
                campaign = await self.campaign_manager.get_campaign(campaign_id)

                if not campaign or campaign.status != CampaignStatus.ACTIVE:
                    logger.info(f"🛑 Кампания {campaign_id} остановлена или завершена")
                    break

                # Используем MessageSender для отправки пачки
                from cold_outreach.core.message_sender import message_sender

                batch_result = await message_sender.send_campaign_batch(
                    campaign_id=campaign_id,
                    batch_size=5
                )

                # Обрабатываем результат
                if batch_result.get("status") == "no_more_leads":
                    logger.info(f"✅ Кампания {campaign_id} завершена - больше нет лидов")
                    await self.campaign_manager.finalize_campaign(campaign_id)
                    break

                if "error" in batch_result:
                    logger.error(f"❌ Ошибка в кампании {campaign_id}: {batch_result['error']}")
                    break

                # Логируем прогресс
                batch_info = batch_result.get("batch_results", {})
                successful = batch_info.get("successful_sends", 0)
                failed = batch_info.get("failed_sends", 0)

                logger.info(f"📊 Пачка кампании {campaign_id}: {successful} успешно, {failed} неудачно")

                # Если все сессии заблокированы - увеличиваем паузу
                if batch_info.get("rate_limited", 0) == batch_info.get("total_leads", 0):
                    logger.warning(f"⏳ Все сессии заблокированы для кампании {campaign_id}, пауза 10 минут")
                    await asyncio.sleep(600)  # 10 минут
                    continue

                # Обычная пауза между пачками
                await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"❌ Критическая ошибка в кампании {campaign_id}: {e}")
            # Помечаем кампанию как failed
            try:
                await self.campaign_manager.update_campaign_status(campaign_id, CampaignStatus.FAILED)
            except:
                pass

    # async def _process_lead_in_campaign(self, campaign_id: int, lead_data: Dict):
    #     """Обработка отдельного лида в кампании"""
    #
    #     try:
    #         # Получаем доступную сессию
    #         session_names = await self.campaign_manager.get_campaign_sessions(campaign_id)
    #
    #         available_session = None
    #         for session_name in session_names:
    #             if await self.rate_limiter.can_send_message(session_name):
    #                 if not await self.error_handler.is_session_blocked(session_name):
    #                     available_session = session_name
    #                     break
    #
    #         if not available_session:
    #             logger.info(f"⏳ Нет доступных сессий для лида {lead_data['username']}")
    #             return
    #
    #         # Генерируем сообщение
    #         message_text = await self.campaign_manager.generate_message_for_lead(campaign_id, lead_data)
    #
    #         if not message_text:
    #             logger.error(f"❌ Не удалось сгенерировать сообщение для лида {lead_data['username']}")
    #             return
    #
    #         # Отправляем сообщение
    #         from core.integrations.telegram_client import telegram_session_manager
    #
    #         success = await telegram_session_manager.send_message(
    #             session_name=available_session,
    #             username=lead_data["username"],
    #             message=message_text
    #         )
    #
    #         if success:
    #             # Записываем успешную отправку
    #             await self.campaign_manager.record_message_sent(
    #                 campaign_id, lead_data["id"], available_session, message_text
    #             )
    #
    #             # Обновляем лимиты
    #             await self.rate_limiter.record_message_sent(available_session)
    #
    #             logger.info(f"📤 Отправлено: {available_session} → {lead_data['username']}")
    #
    #         else:
    #             # Записываем неудачу
    #             await self.campaign_manager.record_message_failed(
    #                 campaign_id, lead_data["id"], available_session
    #             )
    #
    #     except Exception as e:
    #         logger.error(f"❌ Ошибка обработки лида {lead_data.get('username', 'unknown')}: {e}")

    async def get_active_campaigns(self) -> List[Dict]:
        """Получение активных кампаний"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(OutreachCampaign)
                    .where(OutreachCampaign.status == CampaignStatus.ACTIVE)
                    .order_by(OutreachCampaign.created_at.desc())
                )
                campaigns = result.scalars().all()

                return [
                    await self.campaign_manager.get_campaign_progress(campaign.id)
                    for campaign in campaigns
                ]

        except Exception as e:
            logger.error(f"❌ Ошибка получения активных кампаний: {e}")
            return []

    async def get_session_outreach_stats(self) -> Dict[str, Dict]:
        """Получение статистики сессий для рассылки"""

        try:
            # Получаем статистику от rate limiter
            rate_stats = await self.rate_limiter.get_sessions_stats()

            # Получаем режимы сессий
            session_modes = self.session_controller.get_all_session_modes()

            # Объединяем данные
            combined_stats = {}

            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.status == SessionStatus.ACTIVE)
                )
                sessions = result.scalars().all()

                for session in sessions:
                    session_name = session.session_name

                    combined_stats[session_name] = {
                        "mode": session_modes.get(session_name, "response").value,
                        "can_send": rate_stats.get(session_name, {}).get("can_send", False),
                        "daily_sent": rate_stats.get(session_name, {}).get("daily_sent", 0),
                        "daily_limit": rate_stats.get(session_name, {}).get("daily_limit", 0),
                        "is_blocked": await self.error_handler.is_session_blocked(session_name),
                        "is_premium": rate_stats.get(session_name, {}).get("is_premium", False)
                    }

            return combined_stats

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики сессий: {e}")
            return {}

    async def shutdown(self):
        """Завершение работы менеджера"""
        try:
            # Возвращаем все сессии в режим ответов
            await self.session_controller.force_switch_all_to_response()

            logger.info("✅ OutreachManager завершен")

        except Exception as e:
            logger.error(f"❌ Ошибка завершения OutreachManager: {e}")


# Глобальный экземпляр менеджера
outreach_manager = OutreachManager()