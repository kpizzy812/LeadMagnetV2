# utils/__init__.py
"""
Утилиты для Lead Management System
Включает системы восстановления соединений и диалогов
"""

from .reconnect_system import reconnect_manager, ReconnectManager, ConnectionState
from .dialog_recovery import dialog_recovery, DialogRecovery
from .proxy_validator import proxy_validator, ProxyValidator, ProxyInfo

__all__ = [
    # Менеджеры
    'reconnect_manager',
    'dialog_recovery',
    'proxy_validator',

    # Классы
    'ReconnectManager',
    'DialogRecovery',
    'ProxyValidator',

    # Enums/Dataclasses
    'ConnectionState',
    'ProxyInfo'
]