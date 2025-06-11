# cold_outreach/safety/rate_limiter.py

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy import select, update
from dataclasses import dataclass

from storage.database import get_db
from storage.models.base import Session
from storage.models.cold_outreach import CampaignSessionAssignment
from loguru import logger


@dataclass
class SessionLimits:
    """Лимиты для сессии"""
    daily_limit: int
    hourly_limit: int
    is_premium: bool
    current_daily_sent: int = 0
    current_hourly_sent: int = 0
    last_reset_date: Optional[datetime] = None
    last_reset_hour: Optional[int] = None


class RateLimiter:
    """Система ограничения скорости отправки для холодной рассылки"""

    def __init__(self):
        self.session_limits: Dict[str, SessionLimits] = {}
        self.send_history: Dict[str, list] = {}  # История отправки по сессиям
        self.last_send_time: Dict[str, datetime] = {}

        # Базовые лимиты
        self.base_limits = {
            "regular": {
                "daily": 5,
                "hourly": 2,
                "min_delay": 1800  # 30 минут между сообщениями
            },
            "premium": {
                "daily": 20,
                "hourly": 8,
                "min_delay": 900  # 15 минут между сообщениями
            }
        }

    async def initialize(self):
        """Инициализация системы лимитов"""
        try:
            await self._load_session_limits()
            logger.info("✅ RateLimiter инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации RateLimiter: {e}")
            raise

    async def _load_session_limits(self):
        """Загрузка лимитов для всех сессий"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Session).where(Session.status == "active")
                )
                sessions = result.scalars().all()

                for session in sessions:
                    # Определяем тип сессии (обычная или премиум)
                    is_premium = await self._is_premium_session(session.session_name)

                    limits_config = self.base_limits["premium" if is_premium else "regular"]

                    self.session_limits[session.session_name] = SessionLimits(
                        daily_limit=limits_config["daily"],
                        hourly_limit=limits_config["hourly"],
                        is_premium=is_premium,
                        last_reset_date=datetime.now().date(),
                        last_reset_hour=datetime.now().hour
                    )

                logger.info(f"📊 Загружены лимиты для {len(self.session_limits)} сессий")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки лимитов сессий: {e}")

    async def _is_premium_session(self, session_name: str) -> bool:
        """Проверка является ли сессия премиум"""

        try:
            # Здесь можно добавить логику определения премиум сессий
            # Например, по названию, по метаданным в БД, или внешнему API

            # Пока простая проверка по названию
            premium_keywords = ["premium", "pro", "vip", "plus"]
            return any(keyword in session_name.lower() for keyword in premium_keywords)

        except Exception as e:
            logger.error(f"❌ Ошибка проверки премиум статуса {session_name}: {e}")
            return False

    async def can_send_message(self, session_name: str) -> bool:
        """Проверка может ли сессия отправить сообщение"""

        try:
            # Обновляем счетчики если нужно
            await self._update_counters(session_name)

            limits = self.session_limits.get(session_name)
            if not limits:
                logger.warning(f"⚠️ Лимиты для сессии {session_name} не найдены")
                return False

            # Проверяем дневной лимит
            if limits.current_daily_sent >= limits.daily_limit:
                logger.debug(
                    f"🚫 Сессия {session_name} достигла дневного лимита ({limits.current_daily_sent}/{limits.daily_limit})")
                return False

            # Проверяем часовой лимит
            if limits.current_hourly_sent >= limits.hourly_limit:
                logger.debug(
                    f"🚫 Сессия {session_name} достигла часового лимита ({limits.current_hourly_sent}/{limits.hourly_limit})")
                return False

            # Проверяем минимальную задержку между сообщениями
            if not await self._check_min_delay(session_name):
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка проверки лимитов для {session_name}: {e}")
            return False

    async def _update_counters(self, session_name: str):
        """Обновление счетчиков для сессии"""

        try:
            limits = self.session_limits.get(session_name)
            if not limits:
                return

            now = datetime.now()
            current_date = now.date()
            current_hour = now.hour

            # Сброс дневного счетчика
            if limits.last_reset_date != current_date:
                limits.current_daily_sent = 0
                limits.last_reset_date = current_date
                logger.debug(f"🔄 Сброшен дневной счетчик для {session_name}")

            # Сброс часового счетчика
            if limits.last_reset_hour != current_hour:
                limits.current_hourly_sent = 0
                limits.last_reset_hour = current_hour
                logger.debug(f"🔄 Сброшен часовой счетчик для {session_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления счетчиков для {session_name}: {e}")

    async def _check_min_delay(self, session_name: str) -> bool:
        """Проверка минимальной задержки между сообщениями"""

        try:
            last_send = self.last_send_time.get(session_name)
            if not last_send:
                return True

            limits = self.session_limits.get(session_name)
            if not limits:
                return True

            # Получаем минимальную задержку
            limits_config = self.base_limits["premium" if limits.is_premium else "regular"]
            min_delay = limits_config["min_delay"]

            time_since_last = (datetime.now() - last_send).total_seconds()

            if time_since_last < min_delay:
                logger.debug(f"⏳ Сессия {session_name} должна ждать еще {min_delay - time_since_last:.0f}с")
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка проверки задержки для {session_name}: {e}")
            return True

    async def record_message_sent(self, session_name: str):
        """Записать факт отправки сообщения"""

        try:
            limits = self.session_limits.get(session_name)
            if not limits:
                logger.warning(f"⚠️ Лимиты для сессии {session_name} не найдены при записи")
                return

            # Обновляем счетчики
            limits.current_daily_sent += 1
            limits.current_hourly_sent += 1

            # Записываем время последней отправки
            self.last_send_time[session_name] = datetime.now()

            # Добавляем в историю
            if session_name not in self.send_history:
                self.send_history[session_name] = []

            self.send_history[session_name].append(datetime.now())

            # Ограничиваем историю последними 100 отправками
            if len(self.send_history[session_name]) > 100:
                self.send_history[session_name] = self.send_history[session_name][-100:]

            logger.debug(
                f"📊 Записана отправка для {session_name}: {limits.current_daily_sent}/{limits.daily_limit} за день")

        except Exception as e:
            logger.error(f"❌ Ошибка записи отправки для {session_name}: {e}")

    async def get_session_load(self, session_name: str) -> float:
        """Получение текущей нагрузки сессии (0.0-1.0)"""

        try:
            limits = self.session_limits.get(session_name)
            if not limits:
                return 1.0  # Максимальная нагрузка если лимиты неизвестны

            # Рассчитываем нагрузку по дневному лимиту
            daily_load = limits.current_daily_sent / limits.daily_limit

            # Рассчитываем нагрузку по часовому лимиту
            hourly_load = limits.current_hourly_sent / limits.hourly_limit

            # Возвращаем максимальную нагрузку
            return min(max(daily_load, hourly_load), 1.0)

        except Exception as e:
            logger.error(f"❌ Ошибка расчета нагрузки для {session_name}: {e}")
            return 1.0

    async def get_daily_sent_count(self, session_name: str) -> int:
        """Получение количества отправленных сообщений за день"""

        limits = self.session_limits.get(session_name)
        return limits.current_daily_sent if limits else 0

    async def get_daily_limit(self, session_name: str) -> int:
        """Получение дневного лимита сессии"""

        limits = self.session_limits.get(session_name)
        return limits.daily_limit if limits else 0

    async def get_time_until_next_send(self, session_name: str) -> int:
        """Получение времени до следующей возможной отправки (секунды)"""

        try:
            # Проверяем минимальную задержку
            last_send = self.last_send_time.get(session_name)
            if last_send:
                limits = self.session_limits.get(session_name)
                if limits:
                    limits_config = self.base_limits["premium" if limits.is_premium else "regular"]
                    min_delay = limits_config["min_delay"]

                    time_since_last = (datetime.now() - last_send).total_seconds()
                    if time_since_last < min_delay:
                        return int(min_delay - time_since_last)

            # Проверяем часовой лимит
            await self._update_counters(session_name)
            limits = self.session_limits.get(session_name)

            if limits and limits.current_hourly_sent >= limits.hourly_limit:
                # Ждем до следующего часа
                now = datetime.now()
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                return int((next_hour - now).total_seconds())

            return 0  # Можно отправлять сейчас

        except Exception as e:
            logger.error(f"❌ Ошибка расчета времени до отправки для {session_name}: {e}")
            return 3600  # Час по умолчанию

    async def set_session_limits(
            self,
            session_name: str,
            daily_limit: int,
            hourly_limit: int,
            is_premium: bool = False
    ):
        """Установка кастомных лимитов для сессии"""

        try:
            self.session_limits[session_name] = SessionLimits(
                daily_limit=daily_limit,
                hourly_limit=hourly_limit,
                is_premium=is_premium,
                last_reset_date=datetime.now().date(),
                last_reset_hour=datetime.now().hour
            )

            logger.info(f"📊 Установлены лимиты для {session_name}: {daily_limit}/день, {hourly_limit}/час")

        except Exception as e:
            logger.error(f"❌ Ошибка установки лимитов для {session_name}: {e}")

    async def get_sessions_stats(self) -> Dict[str, Dict]:
        """Получение статистики по всем сессиям"""

        try:
            stats = {}

            for session_name, limits in self.session_limits.items():
                await self._update_counters(session_name)

                stats[session_name] = {
                    "daily_sent": limits.current_daily_sent,
                    "daily_limit": limits.daily_limit,
                    "hourly_sent": limits.current_hourly_sent,
                    "hourly_limit": limits.hourly_limit,
                    "is_premium": limits.is_premium,
                    "load": await self.get_session_load(session_name),
                    "can_send": await self.can_send_message(session_name),
                    "next_send_in": await self.get_time_until_next_send(session_name),
                    "last_send": self.last_send_time.get(session_name)
                }

            return stats

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики сессий: {e}")
            return {}

    async def reset_session_counters(self, session_name: str):
        """Сброс счетчиков для сессии (экстренный сброс)"""

        try:
            limits = self.session_limits.get(session_name)
            if limits:
                limits.current_daily_sent = 0
                limits.current_hourly_sent = 0

                if session_name in self.last_send_time:
                    del self.last_send_time[session_name]

                logger.info(f"🔄 Счетчики сброшены для сессии {session_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка сброса счетчиков для {session_name}: {e}")

    async def block_session_temporarily(self, session_name: str, duration_minutes: int):
        """Временная блокировка сессии"""

        try:
            limits = self.session_limits.get(session_name)
            if limits:
                # Устанавливаем лимиты в 0 для блокировки
                limits.daily_limit = 0
                limits.hourly_limit = 0

                # Планируем восстановление через указанное время
                asyncio.create_task(
                    self._restore_session_after_delay(session_name, duration_minutes)
                )

                logger.warning(f"🚫 Сессия {session_name} заблокирована на {duration_minutes} минут")

        except Exception as e:
            logger.error(f"❌ Ошибка блокировки сессии {session_name}: {e}")

    async def _restore_session_after_delay(self, session_name: str, delay_minutes: int):
        """Восстановление сессии после задержки"""

        try:
            await asyncio.sleep(delay_minutes * 60)

            # Восстанавливаем лимиты
            is_premium = await self._is_premium_session(session_name)
            limits_config = self.base_limits["premium" if is_premium else "regular"]

            await self.set_session_limits(
                session_name=session_name,
                daily_limit=limits_config["daily"],
                hourly_limit=limits_config["hourly"],
                is_premium=is_premium
            )

            logger.info(f"✅ Сессия {session_name} восстановлена после блокировки")

        except Exception as e:
            logger.error(f"❌ Ошибка восстановления сессии {session_name}: {e}")

# Глобальный экземпляр лимитера скорости
rate_limiter = RateLimiter()