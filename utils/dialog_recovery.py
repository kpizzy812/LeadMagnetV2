# utils/dialog_recovery.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from datetime import datetime, timedelta
from typing import List, Dict, Any
import asyncio
from loguru import logger


class DialogRecovery:
    """Система восстановления пропущенных диалогов с интеграцией"""

    def __init__(self):
        self.last_scan_time: Dict[str, datetime] = {}
        self.recovery_queue = asyncio.Queue()
        self.is_worker_running = False

    async def scan_missed_messages(self, session_name: str, client) -> List[Dict[str, Any]]:
        """Сканирование пропущенных сообщений для сессии"""
        missed_messages = []

        try:
            # Определяем время последнего сканирования
            last_scan = self.last_scan_time.get(session_name)
            if not last_scan:
                # Если первое сканирование, берем последние 2 часа
                last_scan = datetime.now() - timedelta(hours=2)

            logger.info(f"🔍 Сканируем пропущенные сообщения для {session_name} с {last_scan}")

            # Счетчик обработанных диалогов для логирования
            processed_dialogs = 0

            # Получаем диалоги
            async for dialog in client.iter_dialogs():
                # Пропускаем групповые чаты и каналы
                if not dialog.is_user:
                    continue

                processed_dialogs += 1

                # Получаем сообщения с момента последнего сканирования
                async for message in client.iter_messages(
                        dialog,
                        offset_date=last_scan,
                        reverse=True
                ):
                    # Пропускаем исходящие сообщения
                    if message.out:
                        continue

                    # Пропускаем сообщения без текста
                    if not message.text:
                        continue

                    sender = await message.get_sender()
                    if not sender or sender.bot:
                        continue

                    missed_messages.append({
                        "session_name": session_name,
                        "username": sender.username or str(sender.id),
                        "message": message.text,
                        "telegram_id": sender.id,
                        "timestamp": message.date,
                        "message_id": message.id
                    })

                    logger.debug(f"📨 Найдено пропущенное сообщение от @{sender.username}")

            # Обновляем время последнего сканирования
            self.last_scan_time[session_name] = datetime.now()

            if missed_messages:
                logger.info(
                    f"📬 Найдено {len(missed_messages)} пропущенных сообщений для {session_name} из {processed_dialogs} диалогов")
            else:
                logger.info(f"✅ Пропущенных сообщений не найдено в {processed_dialogs} диалогах для {session_name}")

            return missed_messages

        except Exception as e:
            logger.error(f"❌ Ошибка сканирования пропущенных сообщений {session_name}: {e}")
            return []

    async def process_missed_messages(self, missed_messages: List[Dict[str, Any]]):
        """Обработка пропущенных сообщений"""
        if not missed_messages:
            return

        logger.info(f"⚡ Обрабатываем {len(missed_messages)} пропущенных сообщений")

        # Сортируем по времени (старые сначала)
        missed_messages.sort(key=lambda x: x["timestamp"])

        # Добавляем в очередь обработки
        for message_data in missed_messages:
            await self.recovery_queue.put(message_data)

    async def start_recovery_worker(self):
        """Запуск воркера восстановления"""
        if self.is_worker_running:
            logger.warning("⚠️ Воркер восстановления уже запущен")
            return

        self.is_worker_running = True
        logger.info("🔄 Запущен воркер восстановления диалогов")

        while self.is_worker_running:
            try:
                # Получаем сообщение из очереди с таймаутом
                message_data = await asyncio.wait_for(
                    self.recovery_queue.get(),
                    timeout=30
                )

                # Добавляем в основную очередь обработки
                try:
                    from core.handlers.message_handler import message_handler
                    await message_handler.processing_queue.put(message_data)

                    logger.info(f"🔄 Восстановлено сообщение от @{message_data['username']}")

                    # Помечаем задачу как выполненную
                    self.recovery_queue.task_done()

                    # Пауза между обработкой
                    await asyncio.sleep(1)

                except ImportError:
                    logger.error("❌ Не удалось импортировать message_handler")
                    await asyncio.sleep(5)

            except asyncio.TimeoutError:
                # Таймаут - нормально, продолжаем
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка в воркере восстановления: {e}")
                await asyncio.sleep(5)

    async def stop_recovery_worker(self):
        """Остановка воркера восстановления"""
        logger.info("🛑 Остановка воркера восстановления диалогов")
        self.is_worker_running = False

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Получение статистики восстановления"""
        return {
            "queue_size": self.recovery_queue.qsize(),
            "is_worker_running": self.is_worker_running,
            "sessions_tracked": len(self.last_scan_time),
            "last_scan_times": {
                session: scan_time.isoformat()
                for session, scan_time in self.last_scan_time.items()
            }
        }

    async def force_scan_session(self, session_name: str) -> int:
        """Принудительное сканирование конкретной сессии"""
        try:
            # Получаем клиент для сессии
            from core.integrations.telegram_client import telegram_session_manager
            client = await telegram_session_manager.get_client(session_name)

            if not client:
                logger.error(f"❌ Не удалось получить клиент для принудительного сканирования {session_name}")
                return 0

            # Сканируем сообщения
            missed_messages = await self.scan_missed_messages(session_name, client)

            if missed_messages:
                await self.process_missed_messages(missed_messages)

            return len(missed_messages)

        except Exception as e:
            logger.error(f"❌ Ошибка принудительного сканирования {session_name}: {e}")
            return 0

    async def clear_session_history(self, session_name: str):
        """Очистка истории сканирования для сессии"""
        if session_name in self.last_scan_time:
            del self.last_scan_time[session_name]
            logger.info(f"🧹 Очищена история сканирования для {session_name}")


# Глобальный экземпляр
dialog_recovery = DialogRecovery()