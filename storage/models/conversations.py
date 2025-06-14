# storage/models/conversations.py - Модели диалогов и одобрений

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, BigInteger, Index, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum

from .base import Base, TimestampMixin


class ConversationStatus(Enum):
    """Статус диалога"""
    NEW = "new"  # Новый диалог
    PENDING_APPROVAL = "pending_approval"  # Ожидает одобрения админа
    APPROVED = "approved"  # Одобрен админом
    ACTIVE = "active"  # Активный диалог
    PAUSED = "paused"  # Приостановлен
    COMPLETED = "completed"  # Завершен
    BLOCKED = "blocked"  # Заблокирован


class FunnelStage(Enum):
    """Этапы воронки продаж"""
    INITIAL_CONTACT = "initial_contact"
    INTEREST_BUILDING = "interest_building"
    TRUST_BUILDING = "trust_building"
    VALUE_DEMONSTRATION = "value_demonstration"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"
    REF_LINK_SENT = "ref_link_sent"
    CONVERSION = "conversion"


class Conversation(Base, TimestampMixin):
    """Модель диалога - НОВАЯ ВЕРСИЯ для ретроспективной системы"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)

    # Основная информация
    lead_username = Column(String(100), nullable=False, index=True)
    session_name = Column(String(100), nullable=False, index=True)
    lead_telegram_id = Column(BigInteger, nullable=True, index=True)

    # Связи с другими таблицами (опционально)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)

    # НОВОЕ: Статус диалога
    status = Column(String(50), default=ConversationStatus.NEW.value, nullable=False, index=True)

    # НОВОЕ: Флаги для ретроспективной системы
    initiated_by_cold_outreach = Column(Boolean, default=False, nullable=False, index=True)
    admin_approved = Column(Boolean, default=False, nullable=False, index=True)
    requires_approval = Column(Boolean, default=True, nullable=False)

    # НОВОЕ: Отслеживание последних сообщений для ретроспективного сканирования
    last_message_id_from_lead = Column(BigInteger, default=0, nullable=False)  # ID последнего сообщения от лида
    last_message_id_from_us = Column(BigInteger, default=0, nullable=False)  # ID последнего нашего сообщения
    last_scan_timestamp = Column(DateTime, default=func.now(), nullable=False)  # Время последнего сканирования

    # Воронка продаж
    current_stage = Column(String(50), default=FunnelStage.INITIAL_CONTACT.value, nullable=False)
    persona_type = Column(String(50), nullable=True)

    # Прогресс
    ref_link_sent = Column(Boolean, default=False, nullable=False)
    ref_link_sent_at = Column(DateTime, nullable=True)
    converted = Column(Boolean, default=False, nullable=False)
    converted_at = Column(DateTime, nullable=True)

    # Метрики
    total_messages_sent = Column(Integer, default=0, nullable=False)
    total_messages_received = Column(Integer, default=0, nullable=False)
    last_activity = Column(DateTime, default=func.now(), nullable=False)

    # Аналитика времени ответа
    avg_response_time = Column(Float, default=0.0, nullable=False)  # секунды
    last_user_message_at = Column(DateTime, nullable=True)
    last_assistant_message_at = Column(DateTime, nullable=True)

    # Контекст и анализ
    context_summary = Column(Text, nullable=True)  # Краткое резюме диалога
    lead_analysis = Column(JSON, default=dict, nullable=True)  # Анализ лида

    # Дополнительные флаги
    is_whitelisted = Column(Boolean, default=False, nullable=False)  # Добавлен в белый список
    is_blacklisted = Column(Boolean, default=False, nullable=False)  # Добавлен в черный список
    auto_created = Column(Boolean, default=True, nullable=False)  # Создан автоматически или вручную
    ai_disabled = Column(Boolean, default=False, nullable=False)  # Отключение ИИ для конкретного диалога
    auto_responses_paused = Column(Boolean, default=False, nullable=False)  # Пауза автоответов

    # Дополнительные поля
    notes = Column(Text, nullable=True)
    tags = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Связи
    lead = relationship("Lead", back_populates="conversations")
    session = relationship("Session", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    approvals = relationship("MessageApproval", back_populates="conversation", cascade="all, delete-orphan")

    # Индексы для оптимизации ретроспективного сканирования
    __table_args__ = (
        Index('idx_conversation_scan', 'session_name', 'status', 'admin_approved'),
        Index('idx_conversation_messages', 'lead_username', 'session_name', 'last_message_id_from_lead'),
        Index('idx_conversation_approval', 'requires_approval', 'admin_approved', 'status'),
        Index('idx_conversation_cold_outreach', 'initiated_by_cold_outreach', 'status'),
        Index('idx_conversation_active', 'session_name', 'is_active', 'admin_approved'),
        Index('idx_conversation_activity', 'last_activity'),
    )

    @property
    def needs_approval(self) -> bool:
        """Проверка нужно ли одобрение"""
        return self.requires_approval and not self.admin_approved

    @property
    def can_respond(self) -> bool:
        """Может ли ИИ отвечать в этом диалоге"""
        return (
                self.is_active and
                not self.ai_disabled and
                not self.auto_responses_paused and
                not self.is_blacklisted and
                (self.admin_approved or not self.requires_approval)
        )

    def __repr__(self):
        return f"<Conversation {self.lead_username} ↔ {self.session_name} ({self.status})>"


class ApprovalStatus(Enum):
    """Статус одобрения сообщения"""
    PENDING = "pending"  # Ожидает одобрения
    APPROVED = "approved"  # Одобрено
    REJECTED = "rejected"  # Отклонено
    TIMEOUT = "timeout"  # Таймаут (автоматически отклонено)


class MessageApproval(Base, TimestampMixin):
    """Одобрение сообщений админом"""
    __tablename__ = "message_approvals"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)

    # Детали запроса
    lead_username = Column(String(100), nullable=False, index=True)
    session_name = Column(String(100), nullable=False, index=True)
    message_text = Column(Text, nullable=False)
    message_timestamp = Column(DateTime, nullable=False)

    # Статус одобрения
    status = Column(String(20), default=ApprovalStatus.PENDING.value, nullable=False, index=True)
    approved_by_admin_id = Column(BigInteger, nullable=True)  # Telegram ID админа
    approved_at = Column(DateTime, nullable=True)

    # Комментарии
    admin_comment = Column(Text, nullable=True)

    # Связи
    conversation = relationship("Conversation", back_populates="approvals")

    # Индексы
    __table_args__ = (
        Index('idx_approval_status', 'status', 'created_at'),
        Index('idx_approval_conversation', 'conversation_id', 'status'),
        Index('idx_approval_admin', 'approved_by_admin_id', 'approved_at'),
    )

    def __repr__(self):
        return f"<Approval {self.lead_username} ({self.status})>"