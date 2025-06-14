# utils/proxy_error_handler.py - НОВЫЙ компонент для обработки ошибок прокси

import asyncio
import time
from typing import Dict, List, Optional, Set, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import re

from loguru import logger
from telethon.errors import (
    NetworkMigrateError, PhoneMigrateError, ServerError,
    AuthKeyUnregisteredError, AuthKeyInvalidError, AuthKeyDuplicatedError,
    FloodWaitError, TimeoutError as TelethonTimeoutError
)


class ProxyErrorType(Enum):
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    AUTH_FAILED = "auth_failed"
    GENERAL_PROXY_ERROR = "general_proxy_error"
    NETWORK_ERROR = "network_error"
    SERVER_CLOSED = "server_closed"
    UNKNOWN = "unknown"


@dataclass
class ProxyErrorInfo:
    session_name: str
    error_type: ProxyErrorType
    error_message: str
    timestamp: datetime
    proxy_info: str
    retry_count: int = 0


class ProxyErrorHandler:
    """Обработчик ошибок прокси с интеллектуальным анализом и восстановлением"""

    def __init__(self):
        self.error_patterns = {
            ProxyErrorType.TIMEOUT: [
                r"GeneralProxyError.*?timed out",
                r"Socket error.*?timed out",
                r"TimeoutError",
                r"timeout: timed out",
                r"Connection timed out"
            ],
            ProxyErrorType.CONNECTION_REFUSED: [
                r"GeneralProxyError.*?Connection refused",
                r"ConnectionRefusedError",
                r"Connection not allowed by ruleset",
                r"Socket error.*?Connection refused"
            ],
            ProxyErrorType.AUTH_FAILED: [
                r"GeneralProxyError.*?403: Forbidden",
                r"GeneralProxyError.*?407: Proxy Authentication Required",
                r"Authentication failed"
            ],
            ProxyErrorType.SERVER_CLOSED: [
                r"The server closed the connection",
                r"Server closed the connection",
                r"Connection closed while receiving data",
                r"0 bytes read on a total of \d+ expected bytes"
            ],
            ProxyErrorType.GENERAL_PROXY_ERROR: [
                r"GeneralProxyError",
                r"ProxyConnectionError",
                r"SOCKS.*?error"
            ]
        }

        self.session_errors: Dict[str, List[ProxyErrorInfo]] = {}
        self.blocked_sessions: Set[str] = set()
        self.recovery_callbacks: Dict[str, Callable] = {}
        self.error_cooldowns: Dict[str, datetime] = {}

        # Статистика
        self.error_stats = {
            "total_errors": 0,
            "by_type": {error_type: 0 for error_type in ProxyErrorType},
            "by_session": {},
            "recovery_attempts": 0,
            "successful_recoveries": 0
        }

    def analyze_error(self, session_name: str, error_message: str, proxy_info: str = "") -> ProxyErrorInfo:
        """Анализ и классификация ошибки прокси"""

        error_type = self._classify_error(error_message)

        error_info = ProxyErrorInfo(
            session_name=session_name,
            error_type=error_type,
            error_message=error_message,
            timestamp=datetime.now(),
            proxy_info=proxy_info
        )

        # Добавляем в историю
        if session_name not in self.session_errors:
            self.session_errors[session_name] = []

        self.session_errors[session_name].append(error_info)

        # Ограничиваем историю
        if len(self.session_errors[session_name]) > 10:
            self.session_errors[session_name] = self.session_errors[session_name][-10:]

        # Обновляем статистику
        self._update_stats(error_info)

        # Логируем в зависимости от типа ошибки
        self._log_error(error_info)

        return error_info

    def _classify_error(self, error_message: str) -> ProxyErrorType:
        """Классификация ошибки по шаблонам"""
        error_lower = error_message.lower()

        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if re.search(pattern, error_message, re.IGNORECASE):
                    return error_type

        # Дополнительные эвристики
        if "timeout" in error_lower or "timed out" in error_lower:
            return ProxyErrorType.TIMEOUT
        elif "connection" in error_lower and ("refused" in error_lower or "failed" in error_lower):
            return ProxyErrorType.CONNECTION_REFUSED
        elif "server" in error_lower and "closed" in error_lower:
            return ProxyErrorType.SERVER_CLOSED
        elif any(word in error_lower for word in ["proxy", "socks", "http"]):
            return ProxyErrorType.GENERAL_PROXY_ERROR
        elif any(word in error_lower for word in ["network", "connection"]):
            return ProxyErrorType.NETWORK_ERROR

        return ProxyErrorType.UNKNOWN

    def _log_error(self, error_info: ProxyErrorInfo):
        """Логирование ошибки с подавлением спама"""
        session_name = error_info.session_name
        error_type = error_info.error_type

        # Проверяем cooldown для предотвращения спама
        cooldown_key = f"{session_name}:{error_type.value}"
        now = datetime.now()

        if cooldown_key in self.error_cooldowns:
            last_log = self.error_cooldowns[cooldown_key]
            if now - last_log < timedelta(minutes=5):  # Cooldown 5 минут
                return

        self.error_cooldowns[cooldown_key] = now

        # Логируем в зависимости от критичности
        if error_type in [ProxyErrorType.TIMEOUT, ProxyErrorType.SERVER_CLOSED]:
            # Это частые и не критичные ошибки
            logger.debug(f"🔌 {session_name}: {error_type.value} - {error_info.proxy_info}")
        elif error_type in [ProxyErrorType.CONNECTION_REFUSED, ProxyErrorType.AUTH_FAILED]:
            # Это более серьезные ошибки
            logger.warning(f"⚠️ {session_name}: {error_type.value} - {error_info.proxy_info}")
        else:
            # Неизвестные ошибки - логируем полностью
            logger.error(f"❌ {session_name}: {error_type.value} - {error_info.error_message[:100]}...")

    def should_retry_connection(self, session_name: str, error_info: ProxyErrorInfo) -> bool:
        """Определение необходимости повтора подключения"""

        # Получаем историю ошибок для сессии
        session_history = self.session_errors.get(session_name, [])

        # Анализируем последние ошибки
        recent_errors = [
            e for e in session_history
            if datetime.now() - e.timestamp < timedelta(minutes=10)
        ]

        # Не ретраим если слишком много ошибок недавно
        if len(recent_errors) > 5:
            logger.warning(f"🚫 {session_name}: слишком много ошибок за последние 10 минут")
            return False

        # Проверяем тип ошибки
        if error_info.error_type in [ProxyErrorType.AUTH_FAILED]:
            # Ошибки авторизации прокси не ретраим
            return False

        if error_info.error_type in [ProxyErrorType.CONNECTION_REFUSED]:
            # Отказы подключения ретраим ограниченно
            return len(recent_errors) < 2

        # Таймауты и закрытия соединений можно ретраить
        return True

    def get_retry_delay(self, session_name: str, error_info: ProxyErrorInfo) -> float:
        """Расчет задержки перед повтором"""

        session_history = self.session_errors.get(session_name, [])
        recent_errors = [
            e for e in session_history
            if datetime.now() - e.timestamp < timedelta(minutes=30)
        ]

        # Базовая задержка в зависимости от типа ошибки
        base_delays = {
            ProxyErrorType.TIMEOUT: 30.0,
            ProxyErrorType.SERVER_CLOSED: 60.0,
            ProxyErrorType.CONNECTION_REFUSED: 120.0,
            ProxyErrorType.NETWORK_ERROR: 45.0,
            ProxyErrorType.GENERAL_PROXY_ERROR: 90.0,
            ProxyErrorType.UNKNOWN: 60.0
        }

        base_delay = base_delays.get(error_info.error_type, 60.0)

        # Экспоненциальная задержка основанная на количестве недавних ошибок
        error_count = len(recent_errors)
        multiplier = min(2 ** error_count, 16)  # Максимум x16

        return min(base_delay * multiplier, 600.0)  # Максимум 10 минут

    def register_recovery_callback(self, session_name: str, callback: Callable):
        """Регистрация callback для восстановления сессии"""
        self.recovery_callbacks[session_name] = callback

    async def attempt_recovery(self, session_name: str, error_info: ProxyErrorInfo) -> bool:
        """Попытка восстановления сессии после ошибки"""

        if not self.should_retry_connection(session_name, error_info):
            return False

        if session_name not in self.recovery_callbacks:
            logger.warning(f"⚠️ Нет callback для восстановления {session_name}")
            return False

        try:
            self.error_stats["recovery_attempts"] += 1

            # Вычисляем задержку
            delay = self.get_retry_delay(session_name, error_info)
            logger.info(f"🔄 Восстановление {session_name} через {delay:.0f}с (ошибка: {error_info.error_type.value})")

            await asyncio.sleep(delay)

            # Вызываем callback восстановления
            callback = self.recovery_callbacks[session_name]
            success = await callback()

            if success:
                self.error_stats["successful_recoveries"] += 1
                logger.success(f"✅ Сессия {session_name} восстановлена")

                # Очищаем историю ошибок при успешном восстановлении
                if session_name in self.session_errors:
                    self.session_errors[session_name] = []

                return True
            else:
                logger.error(f"❌ Не удалось восстановить сессию {session_name}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка при восстановлении {session_name}: {e}")
            return False

    def block_session(self, session_name: str, reason: str):
        """Блокировка проблемной сессии"""
        self.blocked_sessions.add(session_name)
        logger.error(f"🚫 Сессия {session_name} заблокирована: {reason}")

    def unblock_session(self, session_name: str):
        """Разблокировка сессии"""
        self.blocked_sessions.discard(session_name)
        logger.info(f"✅ Сессия {session_name} разблокирована")

    def is_session_blocked(self, session_name: str) -> bool:
        """Проверка блокировки сессии"""
        return session_name in self.blocked_sessions

    def _update_stats(self, error_info: ProxyErrorInfo):
        """Обновление статистики ошибок"""
        self.error_stats["total_errors"] += 1
        self.error_stats["by_type"][error_info.error_type] += 1

        session_name = error_info.session_name
        if session_name not in self.error_stats["by_session"]:
            self.error_stats["by_session"][session_name] = 0
        self.error_stats["by_session"][session_name] += 1

    def get_session_error_summary(self, session_name: str) -> Dict:
        """Получение сводки ошибок для сессии"""

        if session_name not in self.session_errors:
            return {"total_errors": 0, "recent_errors": 0, "error_types": {}}

        all_errors = self.session_errors[session_name]
        recent_errors = [
            e for e in all_errors
            if datetime.now() - e.timestamp < timedelta(hours=1)
        ]

        # Группируем по типам
        error_types = {}
        for error in recent_errors:
            error_type = error.error_type.value
            if error_type not in error_types:
                error_types[error_type] = 0
            error_types[error_type] += 1

        return {
            "total_errors": len(all_errors),
            "recent_errors": len(recent_errors),
            "error_types": error_types,
            "is_blocked": session_name in self.blocked_sessions,
            "last_error": all_errors[-1].error_message[:100] if all_errors else None,
            "last_error_time": all_errors[-1].timestamp.isoformat() if all_errors else None
        }

    def get_global_error_stats(self) -> Dict:
        """Получение глобальной статистики ошибок"""

        # Топ проблемных сессий
        top_problematic = sorted(
            self.error_stats["by_session"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Статистика по типам ошибок
        error_type_stats = {
            error_type.value: count
            for error_type, count in self.error_stats["by_type"].items()
            if count > 0
        }

        return {
            **self.error_stats,
            "by_type": error_type_stats,
            "top_problematic_sessions": top_problematic,
            "blocked_sessions_count": len(self.blocked_sessions),
            "recovery_success_rate": (
                    self.error_stats["successful_recoveries"] / max(self.error_stats["recovery_attempts"], 1) * 100
            )
        }

    def cleanup_old_errors(self, max_age_hours: int = 24):
        """Очистка старых ошибок"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        cleaned_sessions = 0
        for session_name in list(self.session_errors.keys()):
            old_count = len(self.session_errors[session_name])

            # Фильтруем старые ошибки
            self.session_errors[session_name] = [
                error for error in self.session_errors[session_name]
                if error.timestamp > cutoff_time
            ]

            new_count = len(self.session_errors[session_name])

            # Удаляем пустые записи
            if new_count == 0:
                del self.session_errors[session_name]
                cleaned_sessions += 1

        if cleaned_sessions > 0:
            logger.info(f"🧹 Очищена история ошибок для {cleaned_sessions} сессий")

    def generate_error_report(self) -> str:
        """Генерация отчета об ошибках"""

        stats = self.get_global_error_stats()

        report = "📊 Отчет по ошибкам прокси:\n\n"

        # Общая статистика
        report += f"🔢 Всего ошибок: {stats['total_errors']}\n"
        report += f"🔄 Попыток восстановления: {stats['recovery_attempts']}\n"
        report += f"✅ Успешных восстановлений: {stats['successful_recoveries']}\n"
        report += f"📈 Успешность восстановления: {stats['recovery_success_rate']:.1f}%\n"
        report += f"🚫 Заблокированных сессий: {stats['blocked_sessions_count']}\n\n"

        # Статистика по типам ошибок
        if stats["by_type"]:
            report += "📋 Ошибки по типам:\n"
            for error_type, count in sorted(stats["by_type"].items(), key=lambda x: x[1], reverse=True):
                report += f"   • {error_type}: {count}\n"
            report += "\n"

        # Проблемные сессии
        if stats["top_problematic_sessions"]:
            report += "⚠️ Топ проблемных сессий:\n"
            for session_name, error_count in stats["top_problematic_sessions"][:5]:
                report += f"   • {session_name}: {error_count} ошибок\n"

        return report


# Глобальный экземпляр
proxy_error_handler = ProxyErrorHandler()