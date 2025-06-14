# core/utils/dialog_recovery.py - НОВЫЙ ФАЙЛ
# Система восстановления пропущенных диалогов

from datetime import datetime, timedelta
from typing import List, Any
from typing import Dict
import asyncio
from loguru import logger
import time


class DialogRecovery:
    """Восстановление пропущенных диалогов"""

    def __init__(self):
        self.last_scan_time: Dict[str, datetime] = {}
        self.recovery_queue = asyncio.Queue()

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

            # Получаем диалоги
            async for dialog in client.iter_dialogs():
                # Пропускаем групповые чаты и каналы
                if not dialog.is_user:
                    continue

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
                logger.info(f"📬 Найдено {len(missed_messages)} пропущенных сообщений для {session_name}")

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
        logger.info("🔄 Запущен воркер восстановления диалогов")

        while True:
            try:
                # Получаем сообщение из очереди
                message_data = await asyncio.wait_for(
                    self.recovery_queue.get(),
                    timeout=30
                )

                # Добавляем в основную очередь обработки
                from core.handlers.message_handler import message_handler
                await message_handler.processing_queue.put(message_data)

                logger.info(f"🔄 Восстановлено сообщение от @{message_data['username']}")

                # Пауза между обработкой
                await asyncio.sleep(1)

            except asyncio.TimeoutError:
                # Таймаут - нормально, продолжаем
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка в воркере восстановления: {e}")
                await asyncio.sleep(5)


# Глобальный экземпляр
dialog_recovery = DialogRecovery()