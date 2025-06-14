# core/scanning/retrospective_scanner.py

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass
from sqlalchemy import select, and_, or_, update
from telethon import TelegramClient
from telethon.tl.types import User, PeerUser, Message
from telethon.errors import FloodWaitError, AuthKeyInvalidError, PeerFloodError

from config.settings.base import settings
from storage.database import get_db
from storage.models.base import Session, SessionStatus, Conversation, Message as DBMessage
from core.integrations.telegram.client_factory import TelegramClientFactory
from core.integrations.telegram.proxy_manager import ProxyManager
from core.engine.conversation_manager import conversation_manager
from loguru import logger


@dataclass
class ScanResult:
    """Результат сканирования сессии"""
    session_name: str
    new_messages_count: int
    scanned_dialogs: int
    errors: List[str]
    scan_duration: float
    success: bool


@dataclass
class NewMessageData:
    """Данные нового сообщения"""
    session_name: str
    username: str
    telegram_id: int
    message_text: str
    message_id: int
    timestamp: datetime
    is_from_cold_outreach: bool = False


class RetrospectiveScanner:
    """
    Ретроспективный сканер диалогов - заменяет постоянные обработчики событий.
    Подключается раз в N минут, сканирует все диалоги, обрабатывает новые сообщения.
    """

    def __init__(self):
        self.client_factory = TelegramClientFactory()
        self.proxy_manager = ProxyManager()
        self.scan_interval = settings.system.retrospective_scan_interval  # Из .env
        self.is_running = False
        self.current_scan_task: Optional[asyncio.Task] = None
        self.scan_stats = {
            "total_scans": 0,
            "successful_scans": 0,
            "failed_scans": 0,
            "total_new_messages": 0,
            "average_scan_time": 0.0,
            "last_scan_time": None,
            "next_scan_time": None
        }

    async def start_scanning(self):
        """Запуск ретроспективного сканирования"""
        if self.is_running:
            logger.warning("⚠️ Ретроспективное сканирование уже запущено")
            return

        self.is_running = True
        logger.info(f"🔍 Запуск ретроспективного сканирования (интервал: {self.scan_interval}с)")

        self.current_scan_task = asyncio.create_task(self._scanning_loop())

    async def stop_scanning(self):
        """Остановка сканирования"""
        self.is_running = False
        if self.current_scan_task:
            self.current_scan_task.cancel()
            try:
                await self.current_scan_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Ретроспективное сканирование остановлено")

    async def _scanning_loop(self):
        """Основной цикл сканирования"""
        while self.is_running:
            try:
                # Проверяем не блокирует ли холодная рассылка
                if await self._is_cold_outreach_active():
                    logger.info("📤 Cold outreach активна, пропускаем сканирование")
                    await asyncio.sleep(30)  # Проверяем статус каждые 30 сек
                    continue

                # Обновляем время следующего сканирования
                self.scan_stats["next_scan_time"] = datetime.utcnow() + timedelta(seconds=self.scan_interval)

                # Выполняем сканирование
                await self._perform_full_scan()

                # Ждем до следующего сканирования
                await asyncio.sleep(self.scan_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле ретроспективного сканирования: {e}")
                self.scan_stats["failed_scans"] += 1
                await asyncio.sleep(min(60, self.scan_interval))  # Пауза при ошибке

    async def _is_cold_outreach_active(self) -> bool:
        """Проверка активности холодной рассылки"""
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            from cold_outreach.campaigns.campaign_manager import campaign_manager
            return await campaign_manager.has_active_campaigns()
        except ImportError:
            # Если cold_outreach не установлен
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки холодной рассылки: {e}")
            return False

    async def _perform_full_scan(self):
        """Выполнение полного сканирования всех активных сессий"""
        scan_start = time.time()

        try:
            # Получаем все активные сессии с включенным ИИ
            active_sessions = await self._get_active_sessions()

            if not active_sessions:
                logger.info("📭 Нет активных сессий для сканирования")
                return

            logger.info(f"🔍 Начинаем сканирование {len(active_sessions)} сессий")

            # Сканируем сессии параллельно (но с ограничением)
            semaphore = asyncio.Semaphore(3)  # Максимум 3 одновременных сессии

            scan_tasks = [
                self._scan_session_with_semaphore(semaphore, session)
                for session in active_sessions
            ]

            scan_results = await asyncio.gather(*scan_tasks, return_exceptions=True)

            # Обрабатываем результаты
            await self._process_scan_results(scan_results, scan_start)

        except Exception as e:
            logger.error(f"❌ Ошибка полного сканирования: {e}")
            self.scan_stats["failed_scans"] += 1

    async def _scan_session_with_semaphore(self, semaphore: asyncio.Semaphore, session: Session) -> ScanResult:
        """Сканирование сессии с семафором"""
        async with semaphore:
            return await self._scan_single_session(session)

    async def _scan_single_session(self, session: Session) -> ScanResult:
        """Сканирование одной сессии"""
        session_name = session.session_name
        scan_start = time.time()
        new_messages = []
        errors = []
        scanned_dialogs = 0

        try:
            # Создаем короткоживущий клиент
            client = await self._create_temporary_client(session_name)
            if not client:
                return ScanResult(
                    session_name=session_name,
                    new_messages_count=0,
                    scanned_dialogs=0,
                    errors=["Не удалось создать клиент"],
                    scan_duration=time.time() - scan_start,
                    success=False
                )

            try:
                # Получаем все диалоги с людьми
                dialogs = await self._get_user_dialogs(client)
                scanned_dialogs = len(dialogs)

                logger.debug(f"📊 {session_name}: найдено {scanned_dialogs} диалогов")

                # Сканируем каждый диалог на новые сообщения
                for dialog in dialogs:
                    try:
                        new_msgs = await self._scan_dialog_for_new_messages(
                            client, session_name, dialog
                        )
                        new_messages.extend(new_msgs)
                    except Exception as e:
                        error_msg = f"Ошибка сканирования диалога {dialog.name}: {e}"
                        errors.append(error_msg)
                        logger.debug(f"⚠️ {session_name}: {error_msg}")

                # Обрабатываем найденные новые сообщения
                if new_messages:
                    await self._process_new_messages(new_messages)

            finally:
                # ВАЖНО: Всегда отключаем клиент
                await client.disconnect()

            scan_duration = time.time() - scan_start
            logger.info(
                f"✅ {session_name}: {len(new_messages)} новых сообщений, {scanned_dialogs} диалогов, {scan_duration:.1f}с")

            return ScanResult(
                session_name=session_name,
                new_messages_count=len(new_messages),
                scanned_dialogs=scanned_dialogs,
                errors=errors,
                scan_duration=scan_duration,
                success=True
            )

        except (AuthKeyInvalidError, PeerFloodError) as e:
            error_msg = f"Критическая ошибка сессии: {e}"
            errors.append(error_msg)
            logger.error(f"❌ {session_name}: {error_msg}")

            # Отмечаем сессию как неактивную
            await self._mark_session_inactive(session_name)

        except FloodWaitError as e:
            error_msg = f"Flood wait: {e.seconds}с"
            errors.append(error_msg)
            logger.warning(f"⏰ {session_name}: {error_msg}")

        except Exception as e:
            error_msg = f"Неожиданная ошибка: {e}"
            errors.append(error_msg)
            logger.error(f"❌ {session_name}: {error_msg}")

        return ScanResult(
            session_name=session_name,
            new_messages_count=0,
            scanned_dialogs=scanned_dialogs,
            errors=errors,
            scan_duration=time.time() - scan_start,
            success=False
        )

    async def _create_temporary_client(self, session_name: str) -> Optional[TelegramClient]:
        """Создание короткоживущего клиента"""
        try:
            # Получаем настройки прокси
            proxy_config = await self.proxy_manager.get_proxy_for_session(session_name)

            # Создаем клиент
            client = await self.client_factory.create_client(
                session_name=session_name,
                proxy=proxy_config
            )

            # Подключаемся
            await client.connect()

            # Проверяем авторизацию
            if not await client.is_user_authorized():
                logger.error(f"❌ {session_name}: Клиент не авторизован")
                await client.disconnect()
                return None

            return client

        except Exception as e:
            logger.error(f"❌ {session_name}: Ошибка создания клиента: {e}")
            return None

    async def _get_user_dialogs(self, client: TelegramClient) -> List[Any]:
        """Получение всех диалогов с реальными пользователями"""
        try:
            dialogs = []
            async for dialog in client.iter_dialogs():
                # Только личные чаты с пользователями (не боты, не группы)
                if dialog.is_user and not dialog.entity.bot:
                    dialogs.append(dialog)
            return dialogs
        except Exception as e:
            logger.error(f"❌ Ошибка получения диалогов: {e}")
            return []

    async def _scan_dialog_for_new_messages(self, client: TelegramClient, session_name: str, dialog) -> List[
        NewMessageData]:
        """Сканирование диалога на новые сообщения"""
        try:
            user = dialog.entity
            username = user.username or str(user.id)

            # Получаем последнее обработанное сообщение из БД
            last_processed_msg_id = await self._get_last_processed_message_id(session_name, username)

            # Получаем новые сообщения (только входящие)
            new_messages = []
            async for message in client.iter_messages(dialog, limit=50):
                # Только входящие сообщения (не от нас)
                if message.out:
                    continue

                # Если достигли уже обработанного сообщения - останавливаемся
                if message.id <= last_processed_msg_id:
                    break

                # Проверяем что сообщение не пустое
                if not message.text or len(message.text.strip()) < 1:
                    continue

                # Проверяем был ли диалог инициирован cold outreach
                is_cold_outreach = await self._is_dialog_from_cold_outreach(session_name, username)

                new_messages.append(NewMessageData(
                    session_name=session_name,
                    username=username,
                    telegram_id=user.id,
                    message_text=message.text,
                    message_id=message.id,
                    timestamp=message.date,
                    is_from_cold_outreach=is_cold_outreach
                ))

            # Сортируем по времени (сначала старые)
            new_messages.reverse()
            return new_messages

        except Exception as e:
            logger.error(f"❌ Ошибка сканирования диалога {dialog.name}: {e}")
            return []

    async def _process_new_messages(self, new_messages: List[NewMessageData]):
        """Обработка найденных новых сообщений"""
        try:
            for msg_data in new_messages:
                # Обновляем последний ID сообщения в БД
                await self._update_last_processed_message_id(
                    msg_data.session_name,
                    msg_data.username,
                    msg_data.message_id
                )

                # Решаем нужно ли отвечать
                should_respond = await self._should_respond_to_message(msg_data)

                if should_respond:
                    # Передаем в conversation_manager для генерации ответа
                    await self._handle_message_response(msg_data)
                else:
                    logger.info(f"⏸️ Сообщение от {msg_data.username} требует одобрения админа")
                    # Уведомляем админов о новом неодобренном сообщении
                    await self._notify_admin_about_unapproved_message(msg_data)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки новых сообщений: {e}")

    async def _should_respond_to_message(self, msg_data: NewMessageData) -> bool:
        """Определяет нужно ли отвечать на сообщение автоматически"""
        # Если диалог был инициирован cold outreach - отвечаем автоматически
        if msg_data.is_from_cold_outreach:
            return True

        # Если кто-то левый написал первым - требуется одобрение админа
        # Проверяем есть ли уже диалог в системе
        conversation = await conversation_manager.get_conversation(
            lead_username=msg_data.username,
            session_name=msg_data.session_name,
            create_if_not_exists=False
        )

        if conversation and conversation.admin_approved:
            return True

        return False

    async def _handle_message_response(self, msg_data: NewMessageData):
        """Обработка сообщения через conversation_manager"""
        try:
            # Получаем или создаем диалог
            conversation = await conversation_manager.get_conversation(
                lead_username=msg_data.username,
                session_name=msg_data.session_name,
                create_if_not_exists=True
            )

            if conversation:
                # Обрабатываем сообщение через conversation_manager
                await conversation_manager.process_incoming_message(
                    conversation=conversation,
                    message_text=msg_data.message_text,
                    timestamp=msg_data.timestamp
                )

                logger.info(f"💬 Обработано сообщение: {msg_data.username} → {msg_data.session_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки ответа на сообщение от {msg_data.username}: {e}")

    async def _get_active_sessions(self) -> List[Session]:
        """Получение всех активных сессий"""
        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(
                        and_(
                            Session.status == SessionStatus.ACTIVE,
                            Session.ai_enabled == True
                        )
                    )
                )
                return result.scalars().all()
        except Exception as e:
            logger.error(f"❌ Ошибка получения активных сессий: {e}")
            return []

    async def _get_last_processed_message_id(self, session_name: str, username: str) -> int:
        """Получение ID последнего обработанного сообщения"""
        try:
            async with get_db() as db:
                # Сначала ищем диалог
                conv_result = await db.execute(
                    select(Conversation.id).where(
                        and_(
                            Conversation.lead_username == username,
                            Conversation.session_name == session_name
                        )
                    )
                )
                conversation = conv_result.scalar_one_or_none()

                if not conversation:
                    return 0

                # Ищем последнее входящее сообщение
                msg_result = await db.execute(
                    select(DBMessage.telegram_message_id).where(
                        and_(
                            DBMessage.conversation_id == conversation,
                            DBMessage.is_from_lead == True
                        )
                    ).order_by(DBMessage.telegram_message_id.desc()).limit(1)
                )

                last_msg_id = msg_result.scalar_one_or_none()
                return last_msg_id or 0

        except Exception as e:
            logger.error(f"❌ Ошибка получения последнего ID сообщения для {username}: {e}")
            return 0

    async def _update_last_processed_message_id(self, session_name: str, username: str, message_id: int):
        """Обновление ID последнего обработанного сообщения"""
        # Эта информация будет автоматически обновляться при сохранении сообщения в БД
        # через conversation_manager, так что дополнительных действий не требуется
        pass

    async def _is_dialog_from_cold_outreach(self, session_name: str, username: str) -> bool:
        """Проверка был ли диалог инициирован через cold outreach"""
        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Conversation.initiated_by_cold_outreach).where(
                        and_(
                            Conversation.lead_username == username,
                            Conversation.session_name == session_name
                        )
                    )
                )
                initiated_by_cold = result.scalar_one_or_none()
                return initiated_by_cold or False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки cold outreach для {username}: {e}")
            return False

    async def _mark_session_inactive(self, session_name: str):
        """Отметка сессии как неактивной"""
        try:
            async with get_db() as db:
                await db.execute(
                    update(Session).where(
                        Session.session_name == session_name
                    ).values(
                        status=SessionStatus.INACTIVE,
                        last_error=f"Сессия деактивирована: {datetime.utcnow()}"
                    )
                )
                await db.commit()
                logger.warning(f"⚠️ Сессия {session_name} отмечена как неактивная")
        except Exception as e:
            logger.error(f"❌ Ошибка отметки сессии {session_name} как неактивной: {e}")

    async def _notify_admin_about_unapproved_message(self, msg_data: NewMessageData):
        """Уведомление админов о сообщении требующем одобрения"""
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            from bot.main import bot_manager

            message = f"""🔔 <b>Новое сообщение требует одобрения</b>

👤 <b>От:</b> @{msg_data.username}
🤖 <b>Сессия:</b> {msg_data.session_name}
💬 <b>Сообщение:</b> {msg_data.message_text[:200]}...
🕐 <b>Время:</b> {msg_data.timestamp.strftime('%H:%M:%S')}

❓ Это первое сообщение от неизвестного пользователя."""

            await bot_manager.broadcast_to_admins(message)

        except Exception as e:
            logger.error(f"❌ Ошибка уведомления админов: {e}")

    async def _process_scan_results(self, scan_results: List, scan_start: float):
        """Обработка результатов сканирования"""
        total_new_messages = 0
        successful_sessions = 0
        failed_sessions = 0

        for result in scan_results:
            if isinstance(result, Exception):
                failed_sessions += 1
                logger.error(f"❌ Исключение при сканировании: {result}")
                continue

            if result.success:
                successful_sessions += 1
                total_new_messages += result.new_messages_count
            else:
                failed_sessions += 1

        # Обновляем статистику
        scan_duration = time.time() - scan_start
        self.scan_stats.update({
            "total_scans": self.scan_stats["total_scans"] + 1,
            "successful_scans": self.scan_stats["successful_scans"] + successful_sessions,
            "failed_scans": self.scan_stats["failed_scans"] + failed_sessions,
            "total_new_messages": self.scan_stats["total_new_messages"] + total_new_messages,
            "average_scan_time": (self.scan_stats["average_scan_time"] + scan_duration) / 2,
            "last_scan_time": datetime.utcnow()
        })

        logger.info(
            f"📊 Сканирование завершено: "
            f"{successful_sessions}/{successful_sessions + failed_sessions} сессий, "
            f"{total_new_messages} новых сообщений, "
            f"{scan_duration:.1f}с"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики сканирования"""
        stats = self.scan_stats.copy()
        stats.update({
            "is_running": self.is_running,
            "scan_interval": self.scan_interval,
        })

        # Форматируем даты
        for key in ["last_scan_time", "next_scan_time"]:
            if stats.get(key):
                stats[key] = stats[key].isoformat()

        return stats

    async def force_scan_now(self) -> Dict[str, Any]:
        """Принудительное сканирование сейчас (для админов)"""
        if not self.is_running:
            return {"error": "Сканер не запущен"}

        logger.info("🚀 Принудительное сканирование по запросу админа")
        await self._perform_full_scan()
        return {"success": True, "timestamp": datetime.utcnow().isoformat()}


# Глобальный экземпляр сканера
retrospective_scanner = RetrospectiveScanner()