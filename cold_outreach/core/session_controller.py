# cold_outreach/core/session_controller.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import asyncio
from datetime import datetime
from typing import Dict, Optional, Set, List, Any
from enum import Enum
from sqlalchemy import select, update

from storage.database import get_db
from storage.models.base import Session
from loguru import logger


class SessionMode(str, Enum):
    """Режимы работы сессий"""
    RESPONSE = "response"  # Режим ответов на входящие
    OUTREACH = "outreach"  # Режим рассылки


class SessionController:
    """Контроллер переключения режимов сессий с поддержкой сканирования пропущенных сообщений"""

    def __init__(self):
        self.session_modes: Dict[str, SessionMode] = {}
        self.mode_change_locks: Dict[str, asyncio.Lock] = {}

        # НОВОЕ: Отслеживание времени рассылки для каждой сессии
        self.outreach_start_times: Dict[str, datetime] = {}
        self.outreach_end_times: Dict[str, datetime] = {}

    async def initialize(self):
        """Инициализация контроллера"""
        try:
            # Загружаем текущие режимы всех сессий
            async with get_db() as db:
                result = await db.execute(select(Session))
                sessions = result.scalars().all()

                for session in sessions:
                    # По умолчанию все сессии в режиме ответов
                    self.session_modes[session.session_name] = SessionMode.RESPONSE

            logger.info(f"✅ SessionController инициализирован для {len(self.session_modes)} сессий")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации SessionController: {e}")
            raise

    async def switch_to_outreach_mode(self, session_name: str) -> bool:
        """Переключение сессии в режим рассылки"""

        try:
            # Получаем блокировку для сессии
            if session_name not in self.mode_change_locks:
                self.mode_change_locks[session_name] = asyncio.Lock()

            async with self.mode_change_locks[session_name]:
                current_mode = self.session_modes.get(session_name, SessionMode.RESPONSE)

                if current_mode == SessionMode.OUTREACH:
                    logger.info(f"ℹ️ Сессия {session_name} уже в режиме рассылки")
                    return True

                # НОВОЕ: Записываем время начала рассылки
                self.outreach_start_times[session_name] = datetime.utcnow()

                # Отключаем сессию от системы обработки входящих
                await self._disconnect_from_message_handler(session_name)

                # Переключаем режим
                self.session_modes[session_name] = SessionMode.OUTREACH

                # Обновляем метаданные в БД
                await self._update_session_metadata(session_name, {
                    "outreach_mode": True,
                    "outreach_started_at": self.outreach_start_times[session_name].isoformat()
                })

                logger.info(f"📤 Сессия {session_name} переключена в режим рассылки")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка переключения сессии {session_name} в режим рассылки: {e}")
            return False

    async def switch_to_response_mode(self, session_name: str, scan_missed: bool = True) -> bool:
        """
        Переключение сессии в режим ответов

        Args:
            session_name: Имя сессии
            scan_missed: Сканировать пропущенные сообщения (по умолчанию True)
        """

        try:
            if session_name not in self.mode_change_locks:
                self.mode_change_locks[session_name] = asyncio.Lock()

            async with self.mode_change_locks[session_name]:
                current_mode = self.session_modes.get(session_name, SessionMode.RESPONSE)

                if current_mode == SessionMode.RESPONSE:
                    logger.info(f"ℹ️ Сессия {session_name} уже в режиме ответов")
                    return True

                # НОВОЕ: Записываем время окончания рассылки
                self.outreach_end_times[session_name] = datetime.utcnow()

                # Подключаем сессию к системе обработки входящих
                await self._connect_to_message_handler(session_name)

                # Переключаем режим
                self.session_modes[session_name] = SessionMode.RESPONSE

                # Обновляем метаданные в БД
                await self._update_session_metadata(session_name, {
                    "outreach_mode": False,
                    "outreach_ended_at": self.outreach_end_times[session_name].isoformat()
                })

                logger.info(f"💬 Сессия {session_name} переключена в режим ответов")

                # НОВОЕ: Запускаем сканирование пропущенных сообщений
                if scan_missed and session_name in self.outreach_start_times:
                    await self._schedule_missed_messages_scan(session_name)

                return True

        except Exception as e:
            logger.error(f"❌ Ошибка переключения сессии {session_name} в режим ответов: {e}")
            return False

    async def _schedule_missed_messages_scan(self, session_name: str):
        """Планирование сканирования пропущенных сообщений"""

        try:
            from cold_outreach.core.missed_messages_scanner import missed_messages_scanner

            outreach_start = self.outreach_start_times.get(session_name)
            outreach_end = self.outreach_end_times.get(session_name)

            if not outreach_start or not outreach_end:
                logger.warning(f"⚠️ Нет данных о времени рассылки для {session_name}")
                return

            logger.info(f"🔍 Запуск сканирования пропущенных сообщений для {session_name}")

            # Запускаем сканирование в фоне с задержкой 2 минуты
            asyncio.create_task(
                missed_messages_scanner.schedule_scan_after_session_mode_switch(
                    session_name=session_name,
                    outreach_start_time=outreach_start,
                    delay_minutes=2
                )
            )

        except Exception as e:
            logger.error(f"❌ Ошибка планирования сканирования для {session_name}: {e}")

    async def _disconnect_from_message_handler(self, session_name: str):
        """Отключение сессии от обработчика входящих сообщений"""

        try:
            from core.handlers.message_handler import message_handler

            # Приостанавливаем обработку входящих для этой сессии
            await message_handler.pause_session(session_name)

            logger.debug(f"🔌 Сессия {session_name} отключена от обработчика входящих")

        except Exception as e:
            logger.error(f"❌ Ошибка отключения сессии {session_name} от message_handler: {e}")

    async def _connect_to_message_handler(self, session_name: str):
        """Подключение сессии к обработчику входящих сообщений"""

        try:
            from core.handlers.message_handler import message_handler

            # Возобновляем обработку входящих для этой сессии
            await message_handler.resume_session(session_name)

            logger.debug(f"🔌 Сессия {session_name} подключена к обработчику входящих")

        except Exception as e:
            logger.error(f"❌ Ошибка подключения сессии {session_name} к message_handler: {e}")

    async def _update_session_metadata(self, session_name: str, metadata: Dict):
        """Обновление метаданных сессии"""

        try:
            async with get_db() as db:
                # Получаем текущие метаданные
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if session:
                    # Обновляем метаданные
                    current_metadata = session.proxy_config or {}
                    current_metadata.update(metadata)

                    await db.execute(
                        update(Session)
                        .where(Session.session_name == session_name)
                        .values(
                            proxy_config=current_metadata,
                            last_activity=datetime.utcnow()
                        )
                    )
                    await db.commit()

        except Exception as e:
            logger.error(f"❌ Ошибка обновления метаданных сессии {session_name}: {e}")

    async def get_session_mode(self, session_name: str) -> SessionMode:
        """Получение текущего режима сессии"""
        return self.session_modes.get(session_name, SessionMode.RESPONSE)

    async def is_session_active(self, session_name: str) -> bool:
        """Проверка активности сессии"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                return session and session.status == "active"

        except Exception as e:
            logger.error(f"❌ Ошибка проверки активности сессии {session_name}: {e}")
            return False

    async def get_sessions_by_mode(self, mode: SessionMode) -> Set[str]:
        """Получение сессий по режиму работы"""

        return {
            session_name for session_name, session_mode
            in self.session_modes.items()
            if session_mode == mode
        }

    async def get_outreach_sessions(self) -> Set[str]:
        """Получение сессий в режиме рассылки"""
        return await self.get_sessions_by_mode(SessionMode.OUTREACH)

    async def get_response_sessions(self) -> Set[str]:
        """Получение сессий в режиме ответов"""
        return await self.get_sessions_by_mode(SessionMode.RESPONSE)

    async def force_switch_all_to_response(self, scan_missed: bool = True):
        """
        Принудительное переключение всех сессий в режим ответов

        Args:
            scan_missed: Сканировать пропущенные сообщения для каждой сессии
        """

        logger.info("🔄 Принудительное переключение всех сессий в режим ответов")

        outreach_sessions = list(await self.get_outreach_sessions())

        if not outreach_sessions:
            logger.info("ℹ️ Нет сессий в режиме рассылки")
            return

        # Переключаем все сессии параллельно
        tasks = []
        for session_name in outreach_sessions:
            tasks.append(
                self.switch_to_response_mode(session_name, scan_missed=scan_missed)
            )

        # Выполняем с ограничением по времени
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("⏰ Таймаут переключения сессий")

        logger.info("✅ Все сессии переключены в режим ответов")

    async def get_session_mode_stats(self) -> Dict[str, int]:
        """Получение статистики по режимам сессий"""

        stats = {mode.value: 0 for mode in SessionMode}

        for mode in self.session_modes.values():
            stats[mode.value] += 1

        return stats

    async def cleanup_inactive_sessions(self):
        """Очистка неактивных сессий из контроллера"""

        try:
            active_sessions = set()

            async with get_db() as db:
                result = await db.execute(
                    select(Session.session_name).where(Session.status == "active")
                )
                active_sessions = {row[0] for row in result.fetchall()}

            # Удаляем неактивные сессии из памяти
            inactive_sessions = set(self.session_modes.keys()) - active_sessions

            for session_name in inactive_sessions:
                del self.session_modes[session_name]
                if session_name in self.mode_change_locks:
                    del self.mode_change_locks[session_name]
                # НОВОЕ: Очищаем данные о времени рассылки
                self.outreach_start_times.pop(session_name, None)
                self.outreach_end_times.pop(session_name, None)

            if inactive_sessions:
                logger.info(f"🧹 Очищено {len(inactive_sessions)} неактивных сессий из контроллера")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки неактивных сессий: {e}")

    async def get_session_outreach_metadata(self, session_name: str) -> Dict:
        """Получение метаданных рассылки для сессии"""

        try:
            metadata = {}

            # Добавляем данные о времени рассылки
            if session_name in self.outreach_start_times:
                metadata["outreach_start_time"] = self.outreach_start_times[session_name].isoformat()

            if session_name in self.outreach_end_times:
                metadata["outreach_end_time"] = self.outreach_end_times[session_name].isoformat()

            # Добавляем метаданные из БД
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if session and session.proxy_config:
                    db_metadata = {
                        key: value for key, value in session.proxy_config.items()
                        if key.startswith('outreach_')
                    }
                    metadata.update(db_metadata)

            return metadata

        except Exception as e:
            logger.error(f"❌ Ошибка получения метаданных рассылки для {session_name}: {e}")
            return {}

    def get_all_session_modes(self) -> Dict[str, SessionMode]:
        """Получение всех режимов сессий"""
        return self.session_modes.copy()

    # НОВЫЕ методы для работы с пропущенными сообщениями

    async def bulk_scan_missed_messages_for_campaign(self, session_names: List[str]) -> Dict[str, Any]:
        """Массовое сканирование пропущенных сообщений после завершения кампании"""

        try:
            from cold_outreach.core.missed_messages_scanner import missed_messages_scanner

            # Собираем данные о времени рассылки для всех сессий
            campaign_start = None
            campaign_end = None

            for session_name in session_names:
                if session_name in self.outreach_start_times:
                    start_time = self.outreach_start_times[session_name]
                    if campaign_start is None or start_time < campaign_start:
                        campaign_start = start_time

                if session_name in self.outreach_end_times:
                    end_time = self.outreach_end_times[session_name]
                    if campaign_end is None or end_time > campaign_end:
                        campaign_end = end_time

            if not campaign_start or not campaign_end:
                logger.warning("⚠️ Нет данных о времени кампании для сканирования")
                return {"status": "error", "reason": "no_campaign_times"}

            # Запускаем массовое сканирование
            return await missed_messages_scanner.bulk_scan_after_outreach_campaign(
                session_names=session_names,
                campaign_start_time=campaign_start,
                campaign_end_time=campaign_end
            )

        except Exception as e:
            logger.error(f"❌ Ошибка массового сканирования: {e}")
            return {"status": "error", "reason": str(e)}

    def get_outreach_times_for_session(self, session_name: str) -> Dict[str, Optional[datetime]]:
        """Получение времени начала и окончания рассылки для сессии"""

        return {
            "start_time": self.outreach_start_times.get(session_name),
            "end_time": self.outreach_end_times.get(session_name)
        }

    async def reset_session_outreach_times(self, session_name: str):
        """Сброс времени рассылки для сессии"""

        self.outreach_start_times.pop(session_name, None)
        self.outreach_end_times.pop(session_name, None)

        logger.info(f"🔄 Время рассылки сброшено для сессии {session_name}")


# Глобальный экземпляр контроллера
session_controller = SessionController()