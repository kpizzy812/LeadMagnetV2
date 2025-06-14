# utils/telethon_logger_filter.py - НОВЫЙ компонент для фильтрации логов Telethon

import logging
import re
from typing import Set, Dict, Pattern
from datetime import datetime, timedelta

from loguru import logger


class TelethonLogFilter:
    """Фильтр для подавления избыточных логов Telethon"""

    def __init__(self):
        # Паттерны для подавления
        self.suppress_patterns = [
            # Подавляем повторяющиеся ошибки подключения
            r"Attempt \d+ at connecting failed: GeneralProxyError.*?timed out",
            r"Attempt \d+ at connecting failed: GeneralProxyError.*?Connection refused",
            r"Attempt \d+ at connecting failed: TimeoutError",
            r"Server closed the connection: \d+ bytes read",
            r"Connection closed while receiving data",

            # Подавляем отладочные сообщения о подключении
            r"Connection attempt \d+\.\.\.",
            r"Connecting to \d+\.\d+\.\d+\.\d+:\d+/.*",
            r"Starting send loop",
            r"Starting receive loop",
            r"Waiting for messages to send",
            r"Receiving items from the network",

            # Подавляем повторяющиеся MTProto сообщения
            r"Encrypting \d+ message\(s\) in \d+ bytes for sending",
            r"Assigned msg_id = \d+ to",
            r"Connection success!",
            r"Connection to.*complete!",
        ]

        # Компилируем паттерны
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.suppress_patterns]

        # Счетчики для агрегации
        self.message_counts: Dict[str, int] = {}
        self.last_summary: Dict[str, datetime] = {}

        # Настройки агрегации
        self.summary_interval = timedelta(minutes=5)  # Сводка каждые 5 минут
        self.max_repeated_messages = 3  # Максимум повторений перед подавлением

    def should_suppress_log(self, record: logging.LogRecord) -> bool:
        """Определяет, нужно ли подавить лог-сообщение"""

        message = record.getMessage()

        # Проверяем паттерны для подавления
        for pattern in self.compiled_patterns:
            if pattern.search(message):
                self._count_suppressed_message(message)
                return True

        # Проверяем повторяющиеся сообщения
        if self._is_repeated_message(message):
            return True

        return False

    def _count_suppressed_message(self, message: str):
        """Подсчет подавленных сообщений для сводки"""

        # Упрощаем сообщение для группировки
        simplified = self._simplify_message(message)

        if simplified not in self.message_counts:
            self.message_counts[simplified] = 0

        self.message_counts[simplified] += 1

        # Проверяем, нужно ли показать сводку
        self._check_summary_time()

    def _simplify_message(self, message: str) -> str:
        """Упрощение сообщения для группировки"""

        # Убираем конкретные числа и IP адреса
        simplified = re.sub(r'\d+\.\d+\.\d+\.\d+:\d+', 'IP:PORT', message)
        simplified = re.sub(r'Attempt \d+', 'Attempt N', simplified)
        simplified = re.sub(r'\d+ bytes', 'N bytes', simplified)
        simplified = re.sub(r'msg_id = \d+', 'msg_id = N', simplified)

        return simplified[:100]  # Ограничиваем длину

    def _is_repeated_message(self, message: str) -> bool:
        """Проверка на повторяющееся сообщение"""

        simplified = self._simplify_message(message)

        if simplified not in self.message_counts:
            self.message_counts[simplified] = 0

        self.message_counts[simplified] += 1

        return self.message_counts[simplified] > self.max_repeated_messages

    def _check_summary_time(self):
        """Проверка времени для показа сводки"""

        now = datetime.now()

        # Показываем сводку каждые N минут
        if (not self.last_summary or
                now - max(self.last_summary.values(), default=datetime.min) > self.summary_interval):
            self._show_suppressed_summary()
            self.last_summary[now.strftime("%H:%M")] = now

    def _show_suppressed_summary(self):
        """Показ сводки подавленных сообщений"""

        if not self.message_counts:
            return

        # Топ подавленных сообщений
        top_messages = sorted(
            self.message_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        total_suppressed = sum(self.message_counts.values())

        if total_suppressed > 10:  # Показываем сводку только если много подавленных
            logger.info(f"📊 Подавлено {total_suppressed} повторяющихся Telethon сообщений")

            for message, count in top_messages:
                if count > 5:  # Показываем только часто повторяющиеся
                    logger.debug(f"   • {count}x: {message}")

        # Очищаем счетчики
        self.message_counts.clear()

    def force_summary(self):
        """Принудительный показ сводки"""
        self._show_suppressed_summary()


class TelethonLogHandler(logging.Handler):
    """Обработчик логов Telethon с фильтрацией"""

    def __init__(self, log_filter: TelethonLogFilter):
        super().__init__()
        self.log_filter = log_filter
        self.original_level = logging.WARNING  # По умолчанию показываем только WARNING и выше

    def emit(self, record: logging.LogRecord):
        """Обработка лог-записи"""

        try:
            # Проверяем, нужно ли подавить сообщение
            if self.log_filter.should_suppress_log(record):
                return

            # Пропускаем через loguru с соответствующим уровнем
            message = self.format(record)

            if record.levelno >= logging.ERROR:
                logger.error(f"[Telethon] {message}")
            elif record.levelno >= logging.WARNING:
                logger.warning(f"[Telethon] {message}")
            elif record.levelno >= logging.INFO:
                logger.info(f"[Telethon] {message}")
            else:
                logger.debug(f"[Telethon] {message}")

        except Exception:
            self.handleError(record)


def setup_telethon_logging(verbose: bool = False):
    """Настройка фильтрации логов Telethon"""

    # Создаем фильтр
    log_filter = TelethonLogFilter()

    # Создаем обработчик
    handler = TelethonLogHandler(log_filter)

    # Настраиваем уровень логирования для Telethon
    telethon_loggers = [
        'telethon.network.mtprotosender',
        'telethon.network.connection',
        'telethon.client.telegrambaseclient',
        'telethon.client.updates',
        'telethon.client.downloads',
        'telethon.client.uploads',
        'telethon.crypto.aes',
        'telethon.extensions.messagepacker',
    ]

    for logger_name in telethon_loggers:
        tel_logger = logging.getLogger(logger_name)

        # Очищаем существующие обработчики
        tel_logger.handlers.clear()

        # Добавляем наш обработчик
        tel_logger.addHandler(handler)

        # Устанавливаем уровень
        if verbose:
            tel_logger.setLevel(logging.DEBUG)
        else:
            tel_logger.setLevel(logging.WARNING)

        # Предотвращаем propagation для избежания дублирования
        tel_logger.propagate = False

    logger.info("🔇 Настроена фильтрация логов Telethon")

    return log_filter


def cleanup_telethon_logging():
    """Очистка настроек логирования Telethon"""

    telethon_loggers = [
        'telethon.network.mtprotosender',
        'telethon.network.connection',
        'telethon.client.telegrambaseclient',
        'telethon.client.updates',
        'telethon.client.downloads',
        'telethon.client.uploads',
        'telethon.crypto.aes',
        'telethon.extensions.messagepacker',
    ]

    for logger_name in telethon_loggers:
        tel_logger = logging.getLogger(logger_name)
        tel_logger.handlers.clear()
        tel_logger.setLevel(logging.WARNING)
        tel_logger.propagate = True

    logger.info("🔊 Сброшены настройки логирования Telethon")


# Глобальные переменные
_telethon_log_filter = None


def get_telethon_log_filter() -> TelethonLogFilter:
    """Получение глобального фильтра логов"""
    global _telethon_log_filter

    if _telethon_log_filter is None:
        _telethon_log_filter = setup_telethon_logging()

    return _telethon_log_filter