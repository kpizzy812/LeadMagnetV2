# storage/models/base.py - ОБНОВЛЕННАЯ ВЕРСИЯ (только базовые классы и Lead)

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Index, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

# Базовый класс для всех моделей
Base = declarative_base()


class TimestampMixin:
    """Миксин для автоматических временных меток"""
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class Lead(Base, TimestampMixin):
    """Модель лида"""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)

    # Основная информация
    username = Column(String(100), unique=True, index=True, nullable=False)
    telegram_id = Column(String(50), nullable=True, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)

    # Контактная информация
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)

    # Статус лида
    is_active = Column(Boolean, default=True, nullable=False)
    is_converted = Column(Boolean, default=False, nullable=False)
    conversion_date = Column(DateTime, nullable=True)

    # Анализ лида
    lead_quality_score = Column(Integer, default=0, nullable=False)  # 0-100
    engagement_level = Column(String(20), default="unknown", nullable=False)  # low, medium, high
    estimated_budget = Column(String(50), nullable=True)
    risk_profile = Column(String(50), nullable=True)  # conservative, moderate, aggressive

    # Метаданные
    source = Column(String(100), nullable=True)  # откуда пришел лид
    extra_data = Column(JSON, default=dict, nullable=True)
    notes = Column(Text, nullable=True)

    # Связи
    conversations = relationship("Conversation", back_populates="lead")
    messages = relationship("Message", back_populates="lead")

    # Индексы
    __table_args__ = (
        Index('idx_lead_activity', 'is_active', 'engagement_level'),
        Index('idx_lead_conversion', 'is_converted', 'conversion_date'),
        Index('idx_lead_quality', 'lead_quality_score'),
    )

    def __repr__(self):
        return f"<Lead @{self.username} ({self.engagement_level})>"


# Импорты других моделей для совместимости
from .sessions import Session, SessionStatus, RetrospectiveScanState, ScanLog
from .conversations import Conversation, ConversationStatus, FunnelStage, MessageApproval, ApprovalStatus
from .messages import Message, FollowupSchedule

# Для обратной совместимости экспортируем все
__all__ = [
    'Base',
    'TimestampMixin',
    'Lead',
    'Session',
    'SessionStatus',
    'Conversation',
    'ConversationStatus',
    'FunnelStage',
    'Message',
    'MessageApproval',
    'ApprovalStatus',
    'FollowupSchedule',
    'RetrospectiveScanState',
    'ScanLog'
]