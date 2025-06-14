# core/utils/reconnect_system.py - НОВЫЙ ФАЙЛ
# Добавляем систему реконнекта к существующей архитектуре

import asyncio
import time
from typing import Dict, Set, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class ConnectionState(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class ReconnectConfig:
    max_retries: int = 5
    base_delay: float = 2.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    reset_after: float = 300.0


class ReconnectManager:
    """Менеджер переподключений - добавляем к существующему telegram_client.py"""

    def __init__(self):
        self.session_states: Dict[str, ConnectionState] = {}
        self.retry_counts: Dict[str, int] = {}
        self.last_attempt: Dict[str, float] = {}
        self.reconnect_tasks: Dict[str, asyncio.Task] = {}
        self.config = ReconnectConfig()
        self.callbacks: Dict[str, Callable] = {}

    def register_session(self, session_name: str, reconnect_callback: Callable):
        """Регистрация сессии для мониторинга"""
        self.session_states[session_name] = ConnectionState.DISCONNECTED
        self.retry_counts[session_name] = 0
        self.callbacks[session_name] = reconnect_callback
        logger.info(f"🔧 Зарегистрирована сессия для мониторинга: {session_name}")

    def mark_connected(self, session_name: str):
        """Отметить сессию как подключенную"""
        self.session_states[session_name] = ConnectionState.CONNECTED
        self.retry_counts[session_name] = 0
        if session_name in self.reconnect_tasks:
            self.reconnect_tasks[session_name].cancel()
            del self.reconnect_tasks[session_name]
        logger.success(f"✅ Сессия {session_name} подключена")

    def mark_disconnected(self, session_name: str, start_reconnect: bool = True):
        """Отметить сессию как отключенную и запустить переподключение"""
        if session_name not in self.session_states:
            return

        self.session_states[session_name] = ConnectionState.DISCONNECTED
        logger.warning(f"⚠️ Сессия {session_name} отключена")

        if start_reconnect and session_name not in self.reconnect_tasks:
            task = asyncio.create_task(self._reconnect_loop(session_name))
            self.reconnect_tasks[session_name] = task

    async def _reconnect_loop(self, session_name: str):
        """Цикл переподключения с экспоненциальной задержкой"""
        while self.session_states.get(session_name) != ConnectionState.CONNECTED:
            try:
                if self.retry_counts[session_name] >= self.config.max_retries:
                    logger.error(f"❌ Превышен лимит попыток для {session_name}")
                    self.session_states[session_name] = ConnectionState.FAILED
                    break

                # Сброс счетчика если прошло много времени
                now = time.time()
                if (session_name in self.last_attempt and
                        now - self.last_attempt[session_name] > self.config.reset_after):
                    self.retry_counts[session_name] = 0

                # Вычисляем задержку
                delay = min(
                    self.config.base_delay * (self.config.backoff_multiplier ** self.retry_counts[session_name]),
                    self.config.max_delay
                )

                self.retry_counts[session_name] += 1
                self.last_attempt[session_name] = now
                self.session_states[session_name] = ConnectionState.RECONNECTING

                logger.info(
                    f"🔄 Попытка {self.retry_counts[session_name]} переподключения {session_name} через {delay:.1f}с")
                await asyncio.sleep(delay)

                # Вызываем callback переподключения
                if session_name in self.callbacks:
                    success = await self.callbacks[session_name]()
                    if success:
                        self.mark_connected(session_name)
                        break

            except asyncio.CancelledError:
                logger.info(f"🛑 Переподключение {session_name} отменено")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка переподключения {session_name}: {e}")
                await asyncio.sleep(self.config.base_delay)

    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Завершение работы ReconnectManager...")
        for task in self.reconnect_tasks.values():
            task.cancel()
        await asyncio.gather(*self.reconnect_tasks.values(), return_exceptions=True)
        self.reconnect_tasks.clear()


# Глобальный экземпляр
reconnect_manager = ReconnectManager()