# cold_outreach/core/missed_messages_scanner.py

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from telethon import TelegramClient
from telethon.tl.types import User, PeerUser, Dialog
from telethon.tl.functions.messages import GetHistoryRequest

from storage.database import get_db
from storage.models.base import Conversation, Lead, Session
from core.engine.conversation_manager import conversation_manager
from core.integrations.telegram_client import telegram_session_manager
from loguru import logger


class MissedMessagesScanner:
    """Сканер пропущенных сообщений для сессий после режима рассылки"""

    def __init__(self):
        self.scanning_sessions: Set[str] = set()
        self.last_scan_times: Dict[str, datetime] = {}

    async def scan_missed_messages_for_session(
            self,
            session_name: str,
            outreach_start_time: datetime,
            outreach_end_time: datetime
    ) -> Dict[str, Any]:
        """
        Сканирование пропущенных сообщений для сессии после режима рассылки

        Args:
            session_name: Имя сессии
            outreach_start_time: Время начала рассылки
            outreach_end_time: Время окончания рассылки

        Returns:
            Dict с результатами сканирования
        """

        if session_name in self.scanning_sessions:
            logger.warning(f"⚠️ Сессия {session_name} уже сканируется")
            return {"status": "already_scanning"}

        self.scanning_sessions.add(session_name)

        try:
            logger.info(f"🔍 Начинаем сканирование пропущенных сообщений для {session_name}")

            # Получаем клиент сессии
            client = await telegram_session_manager.get_client(session_name)
            if not client:
                logger.error(f"❌ Не удалось получить клиент для {session_name}")
                return {"status": "error", "reason": "client_not_available"}

            # Получаем все диалоги
            dialogs = await client.get_dialogs()

            results = {
                "status": "completed",
                "session_name": session_name,
                "scan_period": {
                    "start": outreach_start_time.isoformat(),
                    "end": outreach_end_time.isoformat()
                },
                "found_messages": 0,
                "processed_chats": 0,
                "new_conversations": 0,
                "resumed_conversations": 0,
                "errors": []
            }

            # Сканируем каждый диалог
            for dialog in dialogs:
                try:
                    # Пропускаем каналы, группы и ботов
                    if not isinstance(dialog.entity, User) or dialog.entity.bot:
                        continue

                    # Получаем username
                    username = dialog.entity.username
                    if not username:
                        username = str(dialog.entity.id)

                    # Получаем историю сообщений за период рассылки
                    messages = await self._get_messages_in_period(
                        client, dialog, outreach_start_time, outreach_end_time
                    )

                    results["processed_chats"] += 1

                    if messages:
                        logger.info(f"📨 Найдено {len(messages)} пропущенных сообщений от @{username}")
                        results["found_messages"] += len(messages)

                        # Обрабатываем каждое сообщение
                        for message in messages:
                            await self._process_missed_message(
                                session_name, username, message, results
                            )

                    # Добавляем небольшую задержку между запросами
                    await asyncio.sleep(0.5)

                except Exception as e:
                    error_msg = f"Ошибка обработки диалога с {getattr(dialog.entity, 'username', 'unknown')}: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    results["errors"].append(error_msg)

            logger.info(
                f"✅ Сканирование {session_name} завершено: "
                f"{results['found_messages']} сообщений, "
                f"{results['new_conversations']} новых диалогов"
            )

            return results

        except Exception as e:
            logger.error(f"❌ Критическая ошибка сканирования {session_name}: {e}")
            return {
                "status": "error",
                "reason": str(e),
                "session_name": session_name
            }

        finally:
            self.scanning_sessions.discard(session_name)
            self.last_scan_times[session_name] = datetime.utcnow()

    async def _get_messages_in_period(
            self,
            client: TelegramClient,
            dialog: Dialog,
            start_time: datetime,
            end_time: datetime,
            limit: int = 100
    ) -> List:
        """Получение сообщений в указанный период"""

        try:
            # Получаем историю сообщений
            history = await client(GetHistoryRequest(
                peer=dialog.entity,
                offset_date=end_time,
                offset_id=0,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0
            ))

            # Фильтруем сообщения по времени и отправителю
            relevant_messages = []

            for message in history.messages:
                # Проверяем что сообщение в нужном периоде
                if not (start_time <= message.date <= end_time):
                    continue

                # Проверяем что сообщение от пользователя (не от нас)
                if message.from_id and message.from_id.user_id == dialog.entity.id:
                    relevant_messages.append(message)

            return relevant_messages

        except Exception as e:
            logger.error(f"❌ Ошибка получения истории для {dialog.entity.username}: {e}")
            return []

    async def _process_missed_message(
            self,
            session_name: str,
            username: str,
            message,
            results: Dict[str, Any]
    ):
        """Обработка пропущенного сообщения"""

        try:
            # Получаем или создаем диалог
            conversation = await conversation_manager.get_conversation(
                lead_username=username,
                session_name=session_name,
                create_if_not_exists=True
            )

            if not conversation:
                logger.error(f"❌ Не удалось создать диалог для {username}")
                return

            # Проверяем был ли это новый диалог
            if conversation.messages_count == 0:
                results["new_conversations"] += 1
                logger.info(f"🆕 Создан новый диалог с @{username}")
            else:
                results["resumed_conversations"] += 1
                logger.info(f"🔄 Возобновлен диалог с @{username}")

            # Обрабатываем сообщение через основную систему
            message_text = message.message or ""

            if message_text.strip():
                response = await conversation_manager.process_user_message(
                    conversation_id=conversation.id,
                    message_text=message_text
                )

                if response:
                    logger.info(f"✅ Ответ сгенерирован для пропущенного сообщения от @{username}")

                    # Отправляем ответ
                    success = await telegram_session_manager.send_message(
                        session_name=session_name,
                        username=username,
                        message=response
                    )

                    if success:
                        logger.info(f"📤 Ответ отправлен: {session_name} → @{username}")
                    else:
                        logger.error(f"❌ Не удалось отправить ответ: {session_name} → @{username}")

        except Exception as e:
            error_msg = f"Ошибка обработки сообщения от @{username}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            results["errors"].append(error_msg)

    async def bulk_scan_after_outreach_campaign(
            self,
            session_names: List[str],
            campaign_start_time: datetime,
            campaign_end_time: datetime
    ) -> Dict[str, Any]:
        """
        Массовое сканирование пропущенных сообщений после кампании
        """

        logger.info(f"🔍 Запуск массового сканирования для {len(session_names)} сессий")

        overall_results = {
            "total_sessions": len(session_names),
            "successful_scans": 0,
            "failed_scans": 0,
            "total_messages_found": 0,
            "total_new_conversations": 0,
            "session_results": {},
            "started_at": datetime.utcnow().isoformat()
        }

        # Сканируем сессии параллельно, но с ограничением
        semaphore = asyncio.Semaphore(3)  # Максимум 3 сессии одновременно

        async def scan_session_with_semaphore(session_name: str):
            async with semaphore:
                try:
                    result = await self.scan_missed_messages_for_session(
                        session_name, campaign_start_time, campaign_end_time
                    )

                    overall_results["session_results"][session_name] = result

                    if result["status"] == "completed":
                        overall_results["successful_scans"] += 1
                        overall_results["total_messages_found"] += result["found_messages"]
                        overall_results["total_new_conversations"] += result["new_conversations"]
                    else:
                        overall_results["failed_scans"] += 1

                except Exception as e:
                    logger.error(f"❌ Ошибка сканирования {session_name}: {e}")
                    overall_results["failed_scans"] += 1
                    overall_results["session_results"][session_name] = {
                        "status": "error",
                        "reason": str(e)
                    }

        # Запускаем сканирование всех сессий
        tasks = [scan_session_with_semaphore(session_name) for session_name in session_names]
        await asyncio.gather(*tasks, return_exceptions=True)

        overall_results["completed_at"] = datetime.utcnow().isoformat()

        logger.info(
            f"✅ Массовое сканирование завершено: "
            f"{overall_results['successful_scans']}/{overall_results['total_sessions']} успешно, "
            f"{overall_results['total_messages_found']} сообщений найдено"
        )

        return overall_results

    async def schedule_scan_after_session_mode_switch(
            self,
            session_name: str,
            outreach_start_time: datetime,
            delay_minutes: int = 5
    ):
        """
        Планирование сканирования после переключения режима сессии
        """

        logger.info(f"📅 Запланировано сканирование {session_name} через {delay_minutes} минут")

        # Ждем указанное время
        await asyncio.sleep(delay_minutes * 60)

        # Выполняем сканирование
        outreach_end_time = datetime.utcnow()

        result = await self.scan_missed_messages_for_session(
            session_name, outreach_start_time, outreach_end_time
        )

        # Уведомляем админов если найдены сообщения
        if result.get("found_messages", 0) > 0:
            await self._notify_admins_about_missed_messages(session_name, result)

        return result

    async def _notify_admins_about_missed_messages(
            self,
            session_name: str,
            scan_result: Dict[str, Any]
    ):
        """Уведомление админов о найденных пропущенных сообщениях"""

        try:
            from bot.main import bot_manager

            found_messages = scan_result.get("found_messages", 0)
            new_conversations = scan_result.get("new_conversations", 0)
            resumed_conversations = scan_result.get("resumed_conversations", 0)

            text = f"""📨 <b>Найдены пропущенные сообщения!</b>

🤖 <b>Сессия:</b> {session_name}
📊 <b>Результат сканирования:</b>
• Сообщений найдено: {found_messages}
• Новых диалогов: {new_conversations}
• Возобновленных: {resumed_conversations}

🔄 <b>Все сообщения автоматически обработаны</b>
ИИ ответил на каждое пропущенное сообщение."""

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="💬 Открыть диалоги",
                        callback_data="dialogs_list"
                    )
                ]]
            )

            await bot_manager.broadcast_to_admins(text, keyboard)

        except Exception as e:
            logger.error(f"❌ Ошибка уведомления админов: {e}")

    def get_scanning_status(self) -> Dict[str, Any]:
        """Получение статуса сканирования"""

        return {
            "currently_scanning": list(self.scanning_sessions),
            "scanning_count": len(self.scanning_sessions),
            "last_scan_times": {
                session: time.isoformat()
                for session, time in self.last_scan_times.items()
            }
        }


# Глобальный экземпляр сканера
missed_messages_scanner = MissedMessagesScanner()