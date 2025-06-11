# cold_outreach/core/message_sender.py - ОБНОВЛЕННАЯ ВЕРСИЯ

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from telethon.errors import (
    FloodWaitError, UserPrivacyRestrictedError, PeerFloodError,
    ChatWriteForbiddenError, UserBannedInChannelError
)

from core.integrations.telegram_client import telegram_session_manager
from cold_outreach.safety.rate_limiter import rate_limiter
from cold_outreach.safety.error_handler import error_handler
from cold_outreach.campaigns.campaign_manager import campaign_manager
from cold_outreach.templates.template_manager import template_manager
from cold_outreach.templates.channel_post_manager import channel_post_manager
from loguru import logger


class MessageSender:
    """Отправщик сообщений для системы холодной рассылки с поддержкой постов"""

    def __init__(self):
        self.sending_queue = asyncio.Queue()
        self.active_senders: Dict[str, bool] = {}
        self.send_history: Dict[str, List[datetime]] = {}

    async def initialize(self):
        """Инициализация отправщика сообщений"""
        logger.info("✅ MessageSender инициализирован")

    async def send_message_to_lead(
            self,
            session_name: str,
            lead_data: Dict[str, Any],
            template_id: int,
            campaign_id: int
    ) -> Dict[str, Any]:
        """
        Отправка сообщения лиду (включая посты из каналов)

        Returns:
            Dict с результатом отправки
        """

        result = {
            "success": False,
            "session_name": session_name,
            "lead_username": lead_data.get("username"),
            "campaign_id": campaign_id,
            "sent_at": None,
            "error": None,
            "error_type": None,
            "should_retry": False,
            "retry_after": None,
            "message_type": "text"  # НОВОЕ: тип сообщения
        }

        try:
            # 1. Проверяем лимиты отправки
            can_send = await rate_limiter.can_send_message(session_name)
            if not can_send:
                result["error"] = "Rate limit exceeded"
                result["error_type"] = "rate_limit"
                result["retry_after"] = await rate_limiter.get_time_until_next_send(session_name)
                return result

            # 2. Проверяем блокировки сессии
            if await error_handler.is_session_blocked(session_name):
                block_info = await error_handler.get_block_info(session_name)
                result["error"] = f"Session blocked: {block_info.get('type', 'unknown')}"
                result["error_type"] = "session_blocked"
                result["retry_after"] = block_info.get("seconds_left")
                return result

            # 3. Генерируем сообщение из шаблона
            message_content = await template_manager.generate_message_for_lead(
                template_id=template_id,
                lead_data=lead_data
            )

            if not message_content:
                result["error"] = "Failed to generate message from template"
                result["error_type"] = "template_error"
                return result

            # 4. НОВОЕ: Проверяем тип сообщения (пост или текст)
            is_channel_post = message_content.startswith("[FORWARD_POST_TEMPLATE:")

            if is_channel_post:
                # Извлекаем ID шаблона поста
                template_id_from_content = int(message_content.split(":")[1].replace("]", ""))
                template = await template_manager.get_template(template_id_from_content)

                if not template:
                    result["error"] = "Post template not found"
                    result["error_type"] = "template_error"
                    return result

                result["message_type"] = "channel_post"

                # Добавляем человекоподобную задержку
                delay = await self._calculate_send_delay(session_name)
                if delay > 0:
                    await asyncio.sleep(delay)

                # Отправляем пост из канала
                success = await channel_post_manager.send_channel_post(
                    session_name=session_name,
                    username=lead_data["username"],
                    template=template
                )

                if success:
                    result["success"] = True
                    result["sent_at"] = datetime.utcnow()
                    result["message_content"] = f"[POST from @{template.extra_data.get('channel_username', 'unknown')}]"
                else:
                    result["error"] = "Failed to send channel post"
                    result["error_type"] = "send_failed"

            else:
                # Обычное текстовое сообщение
                result["message_type"] = "text"

                # Добавляем человекоподобную задержку
                delay = await self._calculate_send_delay(session_name)
                if delay > 0:
                    await asyncio.sleep(delay)

                # Отправляем текстовое сообщение
                success = await self._send_telegram_message(
                    session_name=session_name,
                    username=lead_data["username"],
                    message=message_content
                )

                if success:
                    result["success"] = True
                    result["sent_at"] = datetime.utcnow()
                    result["message_content"] = message_content[:100] + "..." if len(
                        message_content) > 100 else message_content
                else:
                    result["error"] = "Failed to send text message"
                    result["error_type"] = "send_failed"

            # 5. Обновляем статистику при успехе
            if result["success"]:
                # Обновляем лимиты
                await rate_limiter.record_message_sent(session_name)

                # Записываем в истории отправки
                self._record_send_history(session_name)

                # Записываем в базу данных
                await campaign_manager.record_message_sent(
                    campaign_id=campaign_id,
                    lead_id=lead_data["id"],
                    session_name=session_name,
                    message_text=result["message_content"]
                )

                logger.info(f"✅ {result['message_type'].title()} отправлено: {session_name} → @{lead_data['username']}")
            else:
                result["should_retry"] = True

        except (FloodWaitError, UserPrivacyRestrictedError, PeerFloodError) as e:
            # Обрабатываем через error_handler
            error_info = await error_handler.handle_send_error(
                error=e,
                session_name=session_name,
                campaign_id=campaign_id,
                lead_id=lead_data["id"]
            )

            result["error"] = str(e)
            result["error_type"] = error_info["error_type"]
            result["should_retry"] = error_info.get("action") != "session_banned"
            result["retry_after"] = error_info.get("retry_after")

            # Записываем неудачную отправку
            await campaign_manager.record_message_failed(
                campaign_id=campaign_id,
                lead_id=lead_data["id"],
                session_name=session_name
            )

        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = "unexpected_error"
            result["should_retry"] = True

            logger.error(f"❌ Неожиданная ошибка отправки {session_name} → @{lead_data['username']}: {e}")

        return result

    async def _send_telegram_message(
            self,
            session_name: str,
            username: str,
            message: str
    ) -> bool:
        """Отправка текстового сообщения через Telegram API"""

        try:
            return await telegram_session_manager.send_message(
                session_name=session_name,
                username=username,
                message=message
            )

        except Exception as e:
            logger.error(f"❌ Ошибка Telegram API: {e}")
            # Пробрасываем исключение для обработки в handle_send_error
            raise

    async def _calculate_send_delay(self, session_name: str) -> float:
        """Расчет задержки перед отправкой для имитации человеческого поведения"""

        try:
            # Базовая задержка между сообщениями
            base_delay = random.uniform(3, 8)

            # Дополнительная задержка если недавно отправляли
            recent_sends = self._get_recent_sends(session_name, minutes=10)
            if recent_sends > 0:
                additional_delay = recent_sends * random.uniform(2, 5)
                base_delay += additional_delay

            # Случайная пауза для естественности
            natural_pause = random.uniform(0, 3)

            total_delay = base_delay + natural_pause

            # Ограничиваем максимальную задержку
            return min(total_delay, 30)

        except Exception as e:
            logger.error(f"❌ Ошибка расчета задержки: {e}")
            return random.uniform(5, 10)

    def _get_recent_sends(self, session_name: str, minutes: int = 10) -> int:
        """Получение количества недавних отправок"""

        try:
            if session_name not in self.send_history:
                return 0

            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
            recent_sends = [
                send_time for send_time in self.send_history[session_name]
                if send_time > cutoff_time
            ]

            return len(recent_sends)

        except Exception as e:
            logger.error(f"❌ Ошибка подсчета недавних отправок: {e}")
            return 0

    def _record_send_history(self, session_name: str):
        """Запись времени отправки в историю"""

        try:
            if session_name not in self.send_history:
                self.send_history[session_name] = []

            self.send_history[session_name].append(datetime.utcnow())

            # Ограничиваем историю последними 100 отправками
            if len(self.send_history[session_name]) > 100:
                self.send_history[session_name] = self.send_history[session_name][-100:]

        except Exception as e:
            logger.error(f"❌ Ошибка записи истории отправки: {e}")

    async def bulk_send_to_leads(
            self,
            session_names: List[str],
            leads_batch: List[Dict[str, Any]],
            template_id: int,
            campaign_id: int,
            max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        Массовая отправка сообщений списку лидов (включая посты)

        Args:
            session_names: Список доступных сессий
            leads_batch: Пачка лидов для отправки
            template_id: ID шаблона сообщения
            campaign_id: ID кампании
            max_concurrent: Максимум одновременных отправок
        """

        results = {
            "total_leads": len(leads_batch),
            "successful_sends": 0,
            "failed_sends": 0,
            "rate_limited": 0,
            "blocked_sessions": 0,
            "text_messages": 0,
            "channel_posts": 0,
            "details": [],
            "started_at": datetime.utcnow(),
            "completed_at": None
        }

        # Семафор для ограничения одновременных отправок
        semaphore = asyncio.Semaphore(max_concurrent)

        async def send_to_lead_with_semaphore(lead_data: Dict[str, Any]):
            async with semaphore:
                # Выбираем доступную сессию
                available_session = await self._select_available_session(session_names)

                if not available_session:
                    results["rate_limited"] += 1
                    results["details"].append({
                        "lead_username": lead_data.get("username"),
                        "status": "no_available_session",
                        "session": None,
                        "message_type": "unknown"
                    })
                    return

                # Отправляем сообщение
                send_result = await self.send_message_to_lead(
                    session_name=available_session,
                    lead_data=lead_data,
                    template_id=template_id,
                    campaign_id=campaign_id
                )

                # Обрабатываем результат
                if send_result["success"]:
                    results["successful_sends"] += 1
                    status = "sent"

                    # Подсчитываем типы сообщений
                    if send_result["message_type"] == "channel_post":
                        results["channel_posts"] += 1
                    else:
                        results["text_messages"] += 1

                else:
                    results["failed_sends"] += 1
                    if send_result["error_type"] == "rate_limit":
                        results["rate_limited"] += 1
                        status = "rate_limited"
                    elif send_result["error_type"] == "session_blocked":
                        results["blocked_sessions"] += 1
                        status = "session_blocked"
                    else:
                        status = "failed"

                results["details"].append({
                    "lead_username": lead_data.get("username"),
                    "status": status,
                    "session": available_session,
                    "message_type": send_result.get("message_type", "unknown"),
                    "error": send_result.get("error"),
                    "sent_at": send_result.get("sent_at")
                })

        # Запускаем отправку для всех лидов
        tasks = [send_to_lead_with_semaphore(lead) for lead in leads_batch]
        await asyncio.gather(*tasks, return_exceptions=True)

        results["completed_at"] = datetime.utcnow()
        results["duration_seconds"] = (results["completed_at"] - results["started_at"]).total_seconds()

        logger.info(
            f"📊 Массовая отправка завершена: {results['successful_sends']}/{results['total_leads']} успешно, "
            f"текст: {results['text_messages']}, посты: {results['channel_posts']}, "
            f"за {results['duration_seconds']:.1f}с"
        )

        return results

    async def _select_available_session(self, session_names: List[str]) -> Optional[str]:
        """Выбор доступной сессии для отправки"""

        try:
            available_sessions = []

            for session_name in session_names:
                # Проверяем лимиты
                if not await rate_limiter.can_send_message(session_name):
                    continue

                # Проверяем блокировки
                if await error_handler.is_session_blocked(session_name):
                    continue

                available_sessions.append(session_name)

            if not available_sessions:
                return None

            # Выбираем сессию с наименьшей нагрузкой
            session_loads = {}
            for session_name in available_sessions:
                load = await rate_limiter.get_session_load(session_name)
                session_loads[session_name] = load

            # Сортируем по нагрузке
            sorted_sessions = sorted(session_loads.items(), key=lambda x: x[1])
            return sorted_sessions[0][0]

        except Exception as e:
            logger.error(f"❌ Ошибка выбора доступной сессии: {e}")
            return None

    async def send_campaign_batch(
            self,
            campaign_id: int,
            batch_size: int = 10
    ) -> Dict[str, Any]:
        """Отправка очередной пачки сообщений для кампании"""

        try:
            # Получаем кампанию
            campaign = await campaign_manager.get_campaign(campaign_id)
            if not campaign:
                return {"error": "Campaign not found"}

            # Получаем сессии кампании
            session_names = await campaign_manager.get_campaign_sessions(campaign_id)
            if not session_names:
                return {"error": "No sessions assigned to campaign"}

            # Получаем следующую пачку лидов
            leads_batch = await campaign_manager.get_next_leads_batch(campaign_id, batch_size)
            if not leads_batch:
                return {"status": "no_more_leads"}

            # Отправляем пачку
            send_results = await self.bulk_send_to_leads(
                session_names=session_names,
                leads_batch=leads_batch,
                template_id=campaign.template_id,
                campaign_id=campaign_id,
                max_concurrent=min(len(session_names), 3)
            )

            return {
                "status": "completed",
                "campaign_id": campaign_id,
                "batch_results": send_results
            }

        except Exception as e:
            logger.error(f"❌ Ошибка отправки пачки для кампании {campaign_id}: {e}")
            return {"error": str(e)}

    async def test_session_sending(self, session_name: str, test_username: str) -> Dict[str, Any]:
        """Тестовая отправка сообщения для проверки сессии"""

        try:
            # Проверяем лимиты
            can_send = await rate_limiter.can_send_message(session_name)
            if not can_send:
                return {
                    "success": False,
                    "error": "Rate limit exceeded",
                    "can_retry": True
                }

            # Проверяем блокировки
            if await error_handler.is_session_blocked(session_name):
                return {
                    "success": False,
                    "error": "Session is blocked",
                    "can_retry": False
                }

            # Отправляем тестовое сообщение
            test_message = "Тест соединения"

            success = await telegram_session_manager.send_message(
                session_name=session_name,
                username=test_username,
                message=test_message
            )

            if success:
                await rate_limiter.record_message_sent(session_name)
                self._record_send_history(session_name)

            return {
                "success": success,
                "session_name": session_name,
                "test_username": test_username,
                "sent_at": datetime.utcnow().isoformat() if success else None,
                "error": None if success else "Send failed"
            }

        except Exception as e:
            return {
                "success": False,
                "session_name": session_name,
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def get_sending_stats(self) -> Dict[str, Any]:
        """Получение статистики отправки с разбивкой по типам"""

        try:
            total_sends_24h = 0
            session_stats = {}

            for session_name, send_times in self.send_history.items():
                # Считаем отправки за последние 24 часа
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                recent_sends = [t for t in send_times if t > cutoff_time]

                session_stats[session_name] = {
                    "sends_24h": len(recent_sends),
                    "last_send": send_times[-1].isoformat() if send_times else None,
                    "total_recorded": len(send_times)
                }

                total_sends_24h += len(recent_sends)

            return {
                "total_sends_24h": total_sends_24h,
                "active_senders": len(self.active_senders),
                "session_stats": session_stats,
                "queue_size": self.sending_queue.qsize(),
                "supports_channel_posts": True  # НОВОЕ: индикатор поддержки постов
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики отправки: {e}")
            return {"error": str(e)}

    # Остальные методы остаются без изменений...
    async def start_campaign_sending(self, campaign_id: int):
        """Запуск процесса отправки для кампании"""

        logger.info(f"🚀 Запуск отправки для кампании {campaign_id}")

        try:
            while True:
                # Отправляем очередную пачку
                batch_result = await self.send_campaign_batch(campaign_id, batch_size=5)

                if batch_result.get("status") == "no_more_leads":
                    logger.info(f"✅ Кампания {campaign_id} завершена - больше нет лидов")
                    await campaign_manager.finalize_campaign(campaign_id)
                    break

                if "error" in batch_result:
                    logger.error(f"❌ Ошибка в кампании {campaign_id}: {batch_result['error']}")
                    break

                # Анализируем результаты пачки
                batch_info = batch_result.get("batch_results", {})
                successful = batch_info.get("successful_sends", 0)
                failed = batch_info.get("failed_sends", 0)
                text_msgs = batch_info.get("text_messages", 0)
                posts = batch_info.get("channel_posts", 0)

                logger.info(
                    f"📊 Пачка кампании {campaign_id}: {successful} успешно ({text_msgs} текст, {posts} постов), "
                    f"{failed} неудачно"
                )

                # Если все сессии заблокированы - делаем паузу
                if batch_info.get("rate_limited", 0) == batch_info.get("total_leads", 0):
                    logger.warning(f"⏳ Все сессии заблокированы для кампании {campaign_id}, пауза 10 минут")
                    await asyncio.sleep(600)
                    continue

                # Пауза между пачками
                await asyncio.sleep(random.uniform(60, 120))

        except Exception as e:
            logger.error(f"❌ Критическая ошибка в кампании {campaign_id}: {e}")

    async def emergency_stop_all_sending(self):
        """Экстренная остановка всех отправок"""

        logger.warning("🚨 ЭКСТРЕННАЯ ОСТАНОВКА ВСЕХ ОТПРАВОК")

        try:
            # Очищаем очередь отправки
            while not self.sending_queue.empty():
                try:
                    self.sending_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Помечаем все сессии как неактивные для отправки
            self.active_senders.clear()

            logger.info("✅ Все отправки экстренно остановлены")

        except Exception as e:
            logger.error(f"❌ Ошибка экстренной остановки: {e}")

    def get_queue_status(self) -> Dict[str, Any]:
        """Получение статуса очереди отправки"""

        return {
            "queue_size": self.sending_queue.qsize(),
            "active_senders": list(self.active_senders.keys()),
            "active_senders_count": len(self.active_senders),
            "supports_channel_posts": True
        }


# Глобальный экземпляр отправщика сообщений
message_sender = MessageSender()