# cold_outreach/safety/error_handler.py

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from telethon.errors import (
    FloodWaitError, UserPrivacyRestrictedError, PeerFloodError,
    ChatWriteForbiddenError, UserBannedInChannelError, AuthKeyUnregisteredError
)
from sqlalchemy import select, update

from storage.database import get_db
from storage.models.cold_outreach import SpamBlockRecord, OutreachMessage, OutreachMessageStatus
from loguru import logger


class OutreachErrorHandler:
    """Обработчик ошибок для системы холодной рассылки"""

    def __init__(self):
        self.blocked_sessions: Dict[str, datetime] = {}
        self.flood_wait_sessions: Dict[str, datetime] = {}
        self.recovery_attempts: Dict[str, int] = {}

    async def handle_send_error(
            self,
            error: Exception,
            session_name: str,
            campaign_id: int,
            lead_id: int,
            message_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Основной обработчик ошибок отправки"""

        try:
            error_info = {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "session_name": session_name,
                "campaign_id": campaign_id,
                "lead_id": lead_id,
                "handled": False,
                "action": "none",
                "retry_after": None,
                "block_session": False
            }

            # Обрабатываем разные типы ошибок
            if isinstance(error, FloodWaitError):
                error_info = await self._handle_flood_wait_error(error, session_name, error_info)

            elif isinstance(error, UserPrivacyRestrictedError):
                error_info = await self._handle_privacy_error(error, session_name, error_info)

            elif isinstance(error, PeerFloodError):
                error_info = await self._handle_peer_flood_error(error, session_name, error_info)

            elif isinstance(error, (ChatWriteForbiddenError, UserBannedInChannelError)):
                error_info = await self._handle_banned_error(error, session_name, error_info)

            elif isinstance(error, AuthKeyUnregisteredError):
                error_info = await self._handle_auth_error(error, session_name, error_info)

            else:
                error_info = await self._handle_unknown_error(error, session_name, error_info)

            # Обновляем статус сообщения в БД
            if message_id:
                await self._update_message_status(message_id, error_info)

            # Записываем блокировку если нужно
            if error_info.get("block_session"):
                await self._record_spam_block(session_name, error_info)

            # Логируем обработку
            logger.warning(
                f"⚠️ Ошибка {error_info['error_type']} в сессии {session_name}: "
                f"{error_info['action']}"
            )

            return error_info

        except Exception as e:
            logger.error(f"❌ Ошибка в обработчике ошибок: {e}")
            return {
                "error_type": "HandlerError",
                "error_message": str(e),
                "handled": False,
                "action": "critical_error"
            }

    async def _handle_flood_wait_error(
            self,
            error: FloodWaitError,
            session_name: str,
            error_info: Dict
    ) -> Dict:
        """Обработка FloodWaitError"""

        try:
            wait_seconds = error.seconds
            unblock_time = datetime.utcnow() + timedelta(seconds=wait_seconds)

            # Запоминаем время блокировки
            self.flood_wait_sessions[session_name] = unblock_time

            error_info.update({
                "handled": True,
                "action": f"flood_wait_{wait_seconds}s",
                "retry_after": unblock_time,
                "block_session": True,
                "wait_seconds": wait_seconds
            })

            logger.warning(f"🚫 FloodWait для {session_name}: {wait_seconds}с")

            return error_info

        except Exception as e:
            logger.error(f"❌ Ошибка обработки FloodWait: {e}")
            return error_info

    async def _handle_privacy_error(
            self,
            error: UserPrivacyRestrictedError,
            session_name: str,
            error_info: Dict
    ) -> Dict:
        """Обработка ошибки приватности пользователя"""

        try:
            error_info.update({
                "handled": True,
                "action": "user_privacy_restricted",
                "block_session": False  # Не блокируем сессию
            })

            # Помечаем лида как недоступного для обычных аккаунтов
            await self._mark_lead_privacy_restricted(error_info["lead_id"])

            logger.info(f"🔒 Пользователь ограничил приватность: лид {error_info['lead_id']}")

            return error_info

        except Exception as e:
            logger.error(f"❌ Ошибка обработки privacy error: {e}")
            return error_info

    async def _handle_peer_flood_error(
            self,
            error: PeerFloodError,
            session_name: str,
            error_info: Dict
    ) -> Dict:
        """Обработка PeerFloodError (серьезная блокировка)"""

        try:
            # Длительная блокировка сессии
            block_duration = 24 * 3600  # 24 часа
            unblock_time = datetime.utcnow() + timedelta(seconds=block_duration)

            self.blocked_sessions[session_name] = unblock_time

            error_info.update({
                "handled": True,
                "action": "peer_flood_block_24h",
                "retry_after": unblock_time,
                "block_session": True,
                "wait_seconds": block_duration
            })

            logger.error(f"🚨 PeerFlood для {session_name} - блокировка на 24ч")

            # Планируем восстановление через spambot
            asyncio.create_task(
                self._schedule_spambot_recovery(session_name, delay_hours=2)
            )

            return error_info

        except Exception as e:
            logger.error(f"❌ Ошибка обработки PeerFlood: {e}")
            return error_info

    async def _handle_banned_error(
            self,
            error: Exception,
            session_name: str,
            error_info: Dict
    ) -> Dict:
        """Обработка ошибок бана"""

        try:
            error_info.update({
                "handled": True,
                "action": "session_banned",
                "block_session": True,
                "wait_seconds": 7 * 24 * 3600  # 7 дней
            })

            logger.error(f"🔴 Сессия {session_name} забанена")

            return error_info

        except Exception as e:
            logger.error(f"❌ Ошибка обработки ban error: {e}")
            return error_info

    async def _handle_auth_error(
            self,
            error: AuthKeyUnregisteredError,
            session_name: str,
            error_info: Dict
    ) -> Dict:
        """Обработка ошибки авторизации"""

        try:
            error_info.update({
                "handled": True,
                "action": "auth_key_invalid",
                "block_session": True
            })

            logger.error(f"🔑 Недействительный ключ авторизации для {session_name}")

            return error_info

        except Exception as e:
            logger.error(f"❌ Ошибка обработки auth error: {e}")
            return error_info

    async def _handle_unknown_error(
            self,
            error: Exception,
            session_name: str,
            error_info: Dict
    ) -> Dict:
        """Обработка неизвестных ошибок"""

        try:
            error_message = str(error).lower()

            # Анализируем текст ошибки
            if "flood" in error_message:
                # Пытаемся извлечь время ожидания
                wait_match = re.search(r'(\d+)', error_message)
                wait_seconds = int(wait_match.group(1)) if wait_match else 3600

                error_info.update({
                    "handled": True,
                    "action": f"unknown_flood_{wait_seconds}s",
                    "retry_after": datetime.utcnow() + timedelta(seconds=wait_seconds),
                    "block_session": True,
                    "wait_seconds": wait_seconds
                })

            elif "spam" in error_message:
                error_info.update({
                    "handled": True,
                    "action": "spam_detected",
                    "block_session": True,
                    "wait_seconds": 24 * 3600
                })

            else:
                error_info.update({
                    "handled": False,
                    "action": "unknown_error"
                })

            logger.warning(f"❓ Неизвестная ошибка для {session_name}: {error}")

            return error_info

        except Exception as e:
            logger.error(f"❌ Ошибка обработки unknown error: {e}")
            return error_info

    async def _update_message_status(self, message_id: int, error_info: Dict):
        """Обновление статуса сообщения в БД"""

        try:
            async with get_db() as db:
                status = OutreachMessageStatus.FAILED

                if error_info["error_type"] == "UserPrivacyRestrictedError":
                    status = OutreachMessageStatus.BLOCKED
                elif "flood" in error_info["action"]:
                    status = OutreachMessageStatus.FLOOD_WAIT

                await db.execute(
                    update(OutreachMessage)
                    .where(OutreachMessage.id == message_id)
                    .values(
                        status=status,
                        error_code=error_info["error_type"],
                        error_message=error_info["error_message"],
                        retry_count=OutreachMessage.retry_count + 1,
                        next_retry_at=error_info.get("retry_after")
                    )
                )
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса сообщения {message_id}: {e}")

    async def _record_spam_block(self, session_name: str, error_info: Dict):
        """Запись блокировки в БД"""

        try:
            async with get_db() as db:
                block_record = SpamBlockRecord(
                    session_name=session_name,
                    block_type=error_info["error_type"],
                    error_message=error_info["error_message"],
                    wait_seconds=error_info.get("wait_seconds"),
                    unblock_at=error_info.get("retry_after"),
                    campaign_id=error_info.get("campaign_id")
                )

                db.add(block_record)
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка записи блокировки для {session_name}: {e}")

    async def _mark_lead_privacy_restricted(self, lead_id: int):
        """Пометка лида как ограничившего приватность"""

        try:
            async with get_db() as db:
                from storage.models.cold_outreach import OutreachLead

                await db.execute(
                    update(OutreachLead)
                    .where(OutreachLead.id == lead_id)
                    .values(
                        is_blocked=True,
                        block_reason="privacy_restricted"
                    )
                )
                await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка пометки лида {lead_id} как privacy restricted: {e}")

    async def _schedule_spambot_recovery(self, session_name: str, delay_hours: int = 2):
        """Планирование восстановления через spambot"""

        try:
            await asyncio.sleep(delay_hours * 3600)

            logger.info(f"🔧 Попытка восстановления {session_name} через spambot...")

            # Здесь можно добавить логику отправки /start в @spambot
            # Пока просто логируем
            success = await self._attempt_spambot_recovery(session_name)

            if success:
                # Убираем из заблокированных
                if session_name in self.blocked_sessions:
                    del self.blocked_sessions[session_name]

                logger.info(f"✅ Сессия {session_name} восстановлена через spambot")
            else:
                logger.warning(f"⚠️ Не удалось восстановить {session_name} через spambot")

        except Exception as e:
            logger.error(f"❌ Ошибка восстановления через spambot для {session_name}: {e}")

    async def _attempt_spambot_recovery(self, session_name: str) -> bool:
        """Попытка восстановления через @spambot"""

        try:
            from core.integrations.telegram_client import telegram_session_manager

            # Отправляем /start в @spambot дважды
            for i in range(2):
                success = await telegram_session_manager.send_message(
                    session_name=session_name,
                    username="spambot",
                    message="/start"
                )

                if not success:
                    return False

                await asyncio.sleep(5)

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка восстановления через spambot: {e}")
            return False

    async def is_session_blocked(self, session_name: str) -> bool:
        """Проверка заблокирована ли сессия"""

        try:
            # Проверяем flood wait
            if session_name in self.flood_wait_sessions:
                unblock_time = self.flood_wait_sessions[session_name]
                if datetime.utcnow() < unblock_time:
                    return True
                else:
                    # Время истекло, убираем из заблокированных
                    del self.flood_wait_sessions[session_name]

            # Проверяем общую блокировку
            if session_name in self.blocked_sessions:
                unblock_time = self.blocked_sessions[session_name]
                if datetime.utcnow() < unblock_time:
                    return True
                else:
                    del self.blocked_sessions[session_name]

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка проверки блокировки {session_name}: {e}")
            return True  # В случае ошибки считаем заблокированной для безопасности

    async def get_block_info(self, session_name: str) -> Optional[Dict]:
        """Получение информации о блокировке сессии"""

        try:
            if session_name in self.flood_wait_sessions:
                unblock_time = self.flood_wait_sessions[session_name]
                if datetime.utcnow() < unblock_time:
                    return {
                        "type": "flood_wait",
                        "unblock_at": unblock_time,
                        "seconds_left": int((unblock_time - datetime.utcnow()).total_seconds())
                    }

            if session_name in self.blocked_sessions:
                unblock_time = self.blocked_sessions[session_name]
                if datetime.utcnow() < unblock_time:
                    return {
                        "type": "general_block",
                        "unblock_at": unblock_time,
                        "seconds_left": int((unblock_time - datetime.utcnow()).total_seconds())
                    }

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о блокировке {session_name}: {e}")
            return None

    async def unblock_session_manually(self, session_name: str) -> bool:
        """Ручная разблокировка сессии"""

        try:
            removed = False

            if session_name in self.flood_wait_sessions:
                del self.flood_wait_sessions[session_name]
                removed = True

            if session_name in self.blocked_sessions:
                del self.blocked_sessions[session_name]
                removed = True

            if removed:
                logger.info(f"✅ Сессия {session_name} разблокирована вручную")

            return removed

        except Exception as e:
            logger.error(f"❌ Ошибка ручной разблокировки {session_name}: {e}")
            return False

    async def get_blocked_sessions_stats(self) -> Dict[str, Any]:
        """Статистика заблокированных сессий"""

        try:
            now = datetime.utcnow()

            flood_wait_active = {
                name: time for name, time in self.flood_wait_sessions.items()
                if time > now
            }

            blocked_active = {
                name: time for name, time in self.blocked_sessions.items()
                if time > now
            }

            return {
                "flood_wait_sessions": len(flood_wait_active),
                "blocked_sessions": len(blocked_active),
                "total_blocked": len(flood_wait_active) + len(blocked_active),
                "flood_wait_list": list(flood_wait_active.keys()),
                "blocked_list": list(blocked_active.keys())
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики блокировок: {e}")
            return {
                "flood_wait_sessions": 0,
                "blocked_sessions": 0,
                "total_blocked": 0,
                "flood_wait_list": [],
                "blocked_list": []
            }

# Глобальный экземпляр обработчика ошибок
error_handler = OutreachErrorHandler()