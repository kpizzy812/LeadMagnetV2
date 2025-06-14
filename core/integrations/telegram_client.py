# core/integrations/telegram_client.py - ОБРАТНАЯ СОВМЕСТИМОСТЬ

"""
Файл обратной совместимости для рефакторенного telegram клиента.
Основная логика перенесена в модули core/integrations/telegram/
"""

# Импорты для обратной совместимости
from .telegram.session_manager import TelegramSessionManager
from .telegram.proxy_manager import ProxyManager
from .telegram.client_factory import TelegramClientFactory
from .telegram.connection_monitor import ConnectionMonitor

# Переэкспорт главных классов для совместимости
TelegramSessionManager = TelegramSessionManager
ProxyManager = ProxyManager

# Глобальный экземпляр для совместимости со старым кодом
telegram_session_manager = TelegramSessionManager()

# Для обратной совместимости с кодом, который импортирует отдельные классы:
__all__ = [
    'TelegramSessionManager',
    'ProxyManager',
    'TelegramClientFactory',
    'ConnectionMonitor',
    'telegram_session_manager'
]