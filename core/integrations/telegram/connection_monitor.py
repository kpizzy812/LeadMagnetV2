# core/integrations/telegram/connection_monitor.py
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import (
    NetworkMigrateError, PhoneMigrateError, ServerError,
    AuthKeyUnregisteredError, AuthKeyInvalidError, AuthKeyDuplicatedError
)
from loguru import logger


@dataclass
class ConnectionStatus:
    is_connected: bool
    last_check: datetime
    last_heartbeat: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None


class ConnectionMonitor:
    """Мониторинг соединений Telegram клиентов"""

    def __init__(self):
        self.monitors: Dict[str, asyncio.Task] = {}
        self.statuses: Dict[str, ConnectionStatus] = {}
        self.heartbeats: Dict[str, datetime] = {}
        self.disconnect_callbacks: Dict[str, Callable] = {}

    def start_monitoring(self, session_name: str, client: TelegramClient, disconnect_callback: Callable):
        """Запуск мониторинга для сессии"""

        # Останавливаем существующий мониторинг если есть
        self.stop_monitoring(session_name)

        # Регистрируем callback
        self.disconnect_callbacks[session_name] = disconnect_callback

        # Инициализируем статус
        self.statuses[session_name] = ConnectionStatus(
            is_connected=True,
            last_check=datetime.utcnow()
        )

        # Запускаем задачу мониторинга
        task = asyncio.create_task(self._monitor_session(session_name, client))
        self.monitors[session_name] = task

        # Инициализируем heartbeat
        self.heartbeats[session_name] = datetime.utcnow()

        logger.info(f"🔍 Запущен мониторинг соединения для {session_name}")

    def stop_monitoring(self, session_name: str):
        """Остановка мониторинга для сессии"""
        if session_name in self.monitors:
            self.monitors[session_name].cancel()
            del self.monitors[session_name]

        if session_name in self.statuses:
            del self.statuses[session_name]

        if session_name in self.heartbeats:
            del self.heartbeats[session_name]

        if session_name in self.disconnect_callbacks:
            del self.disconnect_callbacks[session_name]

    def update_heartbeat(self, session_name: str):
        """Обновление heartbeat для сессии"""
        self.heartbeats[session_name] = datetime.utcnow()

        if session_name in self.statuses:
            self.statuses[session_name].last_heartbeat = datetime.utcnow()

    async def _monitor_session(self, session_name: str, client: TelegramClient):
        """Мониторинг конкретной сессии"""
        try:
            while True:
                await asyncio.sleep(30)  # Проверка каждые 30 секунд

                try:
                    # Обновляем время последней проверки
                    if session_name in self.statuses:
                        self.statuses[session_name].last_check = datetime.utcnow()

                    # Проверяем что клиент подключен
                    if not client.is_connected():
                        logger.warning(f"⚠️ Клиент {session_name} отключен")
                        await self._handle_disconnect(session_name, "Client disconnected")
                        break

                    # Проверяем авторизацию
                    if not await client.is_user_authorized():
                        logger.warning(f"⚠️ Клиент {session_name} потерял авторизацию")
                        await self._handle_disconnect(session_name, "Authorization lost")
                        break

                    # Проверяем heartbeat (последняя активность)
                    last_heartbeat = self.heartbeats.get(session_name)
                    if last_heartbeat:
                        inactive_time = datetime.utcnow() - last_heartbeat
                        if inactive_time > timedelta(hours=2):  # Предупреждение если нет активности 2 часа
                            logger.warning(f"💤 Сессия {session_name} неактивна {inactive_time}")

                    # Обновляем статус успешной проверки
                    if session_name in self.statuses:
                        self.statuses[session_name].is_connected = True
                        self.statuses[session_name].error_count = 0
                        self.statuses[session_name].last_error = None

                except (NetworkMigrateError, PhoneMigrateError, ServerError, OSError) as e:
                    logger.error(f"🔌 Ошибка соединения для {session_name}: {e}")
                    await self._handle_disconnect(session_name, f"Connection error: {e}")
                    break

                except (AuthKeyUnregisteredError, AuthKeyInvalidError, AuthKeyDuplicatedError) as e:
                    logger.error(f"🚫 Критическая ошибка авторизации для {session_name}: {e}")
                    await self._handle_disconnect(session_name, f"Auth error: {e}")
                    break

                except Exception as e:
                    # Обновляем счетчик ошибок
                    if session_name in self.statuses:
                        self.statuses[session_name].error_count += 1
                        self.statuses[session_name].last_error = str(e)

                        # Если слишком много ошибок - отключаем
                        if self.statuses[session_name].error_count >= 3:
                            logger.error(f"❌ Слишком много ошибок для {session_name}: {e}")
                            await self._handle_disconnect(session_name, f"Too many errors: {e}")
                            break

                    logger.error(f"❌ Ошибка мониторинга {session_name}: {e}")
                    await asyncio.sleep(60)  # Пауза при ошибке

        except asyncio.CancelledError:
            logger.info(f"🛑 Мониторинг {session_name} остановлен")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка мониторинга {session_name}: {e}")

    async def _handle_disconnect(self, session_name: str, reason: str):
        """Обработка отключения сессии"""
        try:
            # Обновляем статус
            if session_name in self.statuses:
                self.statuses[session_name].is_connected = False
                self.statuses[session_name].last_error = reason

            # Вызываем callback отключения
            if session_name in self.disconnect_callbacks:
                callback = self.disconnect_callbacks[session_name]
                await callback(session_name, reason)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки отключения {session_name}: {e}")

    def get_status(self, session_name: str) -> Optional[ConnectionStatus]:
        """Получение статуса соединения"""
        return self.statuses.get(session_name)

    def get_all_statuses(self) -> Dict[str, ConnectionStatus]:
        """Получение всех статусов"""
        return self.statuses.copy()

    async def cleanup_inactive_monitors(self):
        """Очистка неактивных мониторов"""
        inactive_monitors = []

        for session_name, task in self.monitors.items():
            if task.done():
                inactive_monitors.append(session_name)

        for session_name in inactive_monitors:
            self.stop_monitoring(session_name)

        if inactive_monitors:
            logger.info(f"🧹 Очищено {len(inactive_monitors)} неактивных мониторов")

    async def shutdown(self):
        """Корректное завершение всех мониторов"""
        logger.info("🛑 Завершение ConnectionMonitor...")

        # Отменяем все задачи мониторинга
        for task in self.monitors.values():
            task.cancel()

        # Ждем завершения с таймаутом
        if self.monitors:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.monitors.values(), return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("⏰ Таймаут завершения мониторов")

        self.monitors.clear()
        self.statuses.clear()
        self.heartbeats.clear()
        self.disconnect_callbacks.clear()

        logger.info("✅ ConnectionMonitor завершен")