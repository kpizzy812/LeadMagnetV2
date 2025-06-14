# storage/models/__init__.py

"""
Модели данных для Lead Management System v2.0 (Retrospective)
"""

# Базовые классы
from .base import Base, TimestampMixin, Lead

# Сессии
from .sessions import Session, SessionStatus, RetrospectiveScanState, ScanLog

# Диалоги и одобрения
from .conversations import (
    Conversation, ConversationStatus, FunnelStage,
    MessageApproval, ApprovalStatus
)

# Сообщения и фолоуапы
from .messages import Message, FollowupSchedule

# Аналитика (если есть)
try:
    from .analytics import Analytics
except ImportError:
    Analytics = None

# Cold Outreach модели (если есть)
try:
    from .cold_outreach import (
        OutreachCampaign, OutreachLead, OutreachLeadList,
        CampaignStatus, OutreachMessageStatus
    )
except ImportError:
    pass

# Экспортируем все основные модели
__all__ = [
    # Базовые
    'Base',
    'TimestampMixin',
    'Lead',

    # Сессии
    'Session',
    'SessionStatus',
    'RetrospectiveScanState',
    'ScanLog',

    # Диалоги
    'Conversation',
    'ConversationStatus',
    'FunnelStage',
    'MessageApproval',
    'ApprovalStatus',

    # Сообщения
    'Message',
    'FollowupSchedule',
]

# Добавляем Analytics если доступна
if Analytics:
    __all__.append('Analytics')