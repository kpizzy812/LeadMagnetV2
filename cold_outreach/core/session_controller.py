# cold_outreach/core/session_controller.py

import asyncio
from datetime import datetime
from typing import Dict, Optional, Set
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
    """Контроллер переключения режимов сессий"""

    def __init__(self):
        self.session_modes: Dict[str, SessionMode] = {}
        self.mode_change_locks: Dict[str, asyncio.Lock] = {}

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

                # Отключаем сессию от системы обработки входящих
                await self._disconnect_from_message_handler(session_name)

                # Переключаем режим
                self.session_modes[session_name] = SessionMode.OUTREACH

                # Обновляем метаданные в БД
                await self._update_session_metadata(session_name, {
                    "outreach_mode": True,
                    "outreach_started_at": datetime.utcnow().isoformat()
                })

                logger.info(f"📤 Сессия {session_name} переключена в режим рассылки")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка переключения сессии {session_name} в режим рассылки: {e}")
            return False

    async def switch_to_response_mode(self, session_name: str) -> bool:
        """Переключение сессии в режим ответов"""

        try:
            if session_name not in self.mode_change_locks:
                self.mode_change_locks[session_name] = asyncio.Lock()

            async with self.mode_change_locks[session_name]:
                current_mode = self.session_modes.get(session_name, SessionMode.RESPONSE)

                if current_mode == SessionMode.RESPONSE:
                    logger.info(f"ℹ️ Сессия {session_name} уже в режиме ответов")
                    return True

                # Подключаем сессию к системе обработки входящих
                await self._connect_to_message_handler(session_name)

                # Переключаем режим
                self.session_modes[session_name] = SessionMode.RESPONSE

                # Обновляем метаданные в БД
                await self._update_session_metadata(session_name, {
                    "outreach_mode": False,
                    "outreach_ended_at": datetime.utcnow().isoformat()
                })

                logger.info(f"💬 Сессия {session_name} переключена в режим ответов")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка переключения сессии {session_name} в режим ответов: {e}")
            return False

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

    async def force_switch_all_to_response(self):
        """Принудительное переключение всех сессий в режим ответов"""

        logger.info("🔄 Принудительное переключение всех сессий в режим ответов")

        for session_name in list(self.session_modes.keys()):
            try:
                await self.switch_to_response_mode(session_name)
            except Exception as e:
                logger.error(f"❌ Ошибка переключения сессии {session_name}: {e}")

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

            if inactive_sessions:
                logger.info(f"🧹 Очищено {len(inactive_sessions)} неактивных сессий из контроллера")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки неактивных сессий: {e}")

    async def get_session_outreach_metadata(self, session_name: str) -> Dict:
        """Получение метаданных рассылки для сессии"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = result.scalar_one_or_none()

                if session and session.proxy_config:
                    return {
                        key: value for key, value in session.proxy_config.items()
                        if key.startswith('outreach_')
                    }

            return {}

        except Exception as e:
            logger.error(f"❌ Ошибка получения метаданных рассылки для {session_name}: {e}")
            return {}

    def get_all_session_modes(self) -> Dict[str, SessionMode]:
        """Получение всех режимов сессий"""
        return self.session_modes.copy()