# storage/models/messages.py - Модели сообщений

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, BigInteger, Index, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base, TimestampMixin


class Message(Base, TimestampMixin):
    """Модель сообщения - ОБНОВЛЕННАЯ ВЕРСИЯ для ретроспективного сканирования"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)

    # Связи (опционально)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)

    # НОВОЕ: ID сообщения в Telegram (для ретроспективного сканирования)
    telegram_message_id = Column(BigInteger, nullable=True, index=True)

    # Содержимое
    content = Column(Text, nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    is_from_lead = Column(Boolean, nullable=False, index=True)

    # НОВОЕ: Флаги обработки для ретроспективной системы
    processed_by_retrospective_scan = Column(Boolean, default=False, nullable=False)
    requires_response = Column(Boolean, default=False, nullable=False)
    response_generated = Column(Boolean, default=False, nullable=False)

    # Контекст сообщения
    funnel_stage = Column(String(50), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)  # секунды
    is_followup = Column(Boolean, default=False, nullable=False)

    # Флаги
    processed = Column(Boolean, default=False, nullable=False)

    # Метаданные
    timestamp = Column(DateTime, default=func.now(), nullable=False, index=True)

    # AI метаданные
    ai_prompt_used = Column(Text, nullable=True)
    ai_response_raw = Column(Text, nullable=True)

    # Дополнительные данные
    metadata = Column(JSON, nullable=True)  # JSON для дополнительных данных

    # Связи
    conversation = relationship("Conversation", back_populates="messages")
    lead = relationship("Lead", back_populates="messages")
    session = relationship("Session", back_populates="messages")

    # Индексы для быстрого поиска в ретроспективной системе
    __table_args__ = (
        Index('idx_message_telegram', 'conversation_id', 'telegram_message_id'),
        Index('idx_message_processing', 'processed_by_retrospective_scan', 'requires_response'),
        Index('idx_message_timeline', 'conversation_id', 'timestamp', 'is_from_lead'),
        Index('idx_message_response', 'requires_response', 'response_generated'),
        Index('idx_message_scan_order', 'conversation_id', 'telegram_message_id', 'is_from_lead'),
    )

    @property
    def needs_processing(self) -> bool:
        """Нужна ли обработка сообщения"""
        return not self.processed_by_retrospective_scan and self.is_from_lead

    @property
    def needs_response(self) -> bool:
        """Нужен ли ответ на сообщение"""
        return self.requires_response and not self.response_generated

    def __repr__(self):
        direction = "←" if self.is_from_lead else "→"
        return f"<Message {direction} {self.content[:50]}...>"


class FollowupSchedule(Base, TimestampMixin):
    """Модель расписания фолоуапов"""
    __tablename__ = "followup_schedules"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)

    # Настройки фолоуапа
    followup_type = Column(String(50), nullable=False)  # reminder, value, proof, final
    scheduled_at = Column(DateTime, nullable=False, index=True)
    executed = Column(Boolean, default=False, nullable=False)
    executed_at = Column(DateTime, nullable=True)

    # Содержание
    message_template = Column(Text, nullable=True)
    generated_message = Column(Text, nullable=True)

    # Метаданные
    metadata = Column(JSON, nullable=True)

    # Связи
    conversation = relationship("Conversation")

    # Индексы
    __table_args__ = (
        Index('idx_followup_schedule', 'scheduled_at', 'executed'),
        Index('idx_followup_conversation', 'conversation_id', 'followup_type'),
    )

    def __repr__(self):
        status = "✅" if self.executed else "⏳"
        return f"<Followup {self.followup_type} {status}>"