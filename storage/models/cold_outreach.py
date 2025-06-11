# storage/models/cold_outreach.py

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from typing import Optional, Dict, Any, List

from .base import Base, TimestampMixin  # Используем Base из вашей существующей модели


class CampaignStatus(enum.Enum):
    """Статусы кампании рассылки"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class OutreachMessageStatus(enum.Enum):
    """Статусы отправки сообщений"""
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"
    FLOOD_WAIT = "flood_wait"
    TOO_MANY_REQUESTS = "too_many_requests"


class OutreachLeadList(Base, TimestampMixin):
    """Список лидов для рассылки"""
    __tablename__ = 'outreach_lead_lists'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Статистика списка
    total_leads = Column(Integer, default=0)
    processed_leads = Column(Integer, default=0)
    successful_sends = Column(Integer, default=0)
    failed_sends = Column(Integer, default=0)

    # Метаданные
    source = Column(String(255), nullable=True)
    tags = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)

    # Связи
    leads = relationship("OutreachLead", back_populates="lead_list", cascade="all, delete-orphan")
    campaigns = relationship("OutreachCampaign", back_populates="lead_list")


class OutreachLead(Base, TimestampMixin):
    """Отдельный лид в списке рассылки"""
    __tablename__ = 'outreach_leads'

    id = Column(Integer, primary_key=True)
    lead_list_id = Column(Integer, ForeignKey('outreach_lead_lists.id'), nullable=False)

    # Данные лида
    username = Column(String(100), nullable=False)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    full_name = Column(String(500), nullable=True)

    # Telegram метаданные
    user_id = Column(String(50), nullable=True)
    is_premium = Column(Boolean, nullable=True)
    last_seen = Column(DateTime, nullable=True)

    # Статус обработки
    is_processed = Column(Boolean, default=False)
    last_contact_attempt = Column(DateTime, nullable=True)
    successful_contacts = Column(Integer, default=0)
    failed_contacts = Column(Integer, default=0)

    # Блокировки и ошибки
    is_blocked = Column(Boolean, default=False)
    block_reason = Column(String(255), nullable=True)
    last_error = Column(Text, nullable=True)

    # Связи
    lead_list = relationship("OutreachLeadList", back_populates="leads")
    messages = relationship("OutreachMessage", back_populates="lead")


class OutreachTemplate(Base, TimestampMixin):
    """Шаблон сообщения для рассылки"""
    __tablename__ = 'outreach_templates'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Содержание шаблона
    text = Column(Text, nullable=False)
    variables = Column(JSON, default=list)

    # Настройки персонализации
    persona_type = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)

    # Статистика эффективности
    usage_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)
    avg_response_time = Column(Float, nullable=True)

    # ИИ настройки
    enable_ai_uniquification = Column(Boolean, default=False)
    uniquification_level = Column(String(20), default="medium")

    # Метаданные
    is_active = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)

    # Связи
    campaigns = relationship("OutreachCampaign", back_populates="template")
    messages = relationship("OutreachMessage", back_populates="template")


class OutreachCampaign(Base, TimestampMixin):
    """Кампания холодной рассылки"""
    __tablename__ = 'outreach_campaigns'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Связи с другими моделями
    lead_list_id = Column(Integer, ForeignKey('outreach_lead_lists.id'), nullable=False)
    template_id = Column(Integer, ForeignKey('outreach_templates.id'), nullable=False)

    # Статус и настройки
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT)

    # Настройки рассылки
    max_messages_per_day = Column(Integer, default=50)
    delay_between_messages = Column(Integer, default=1800)
    use_premium_sessions_only = Column(Boolean, default=False)
    enable_spambot_recovery = Column(Boolean, default=True)

    # Временные ограничения
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    daily_start_hour = Column(Integer, default=10)
    daily_end_hour = Column(Integer, default=18)

    # Прогресс и статистика
    total_targets = Column(Integer, default=0)
    processed_targets = Column(Integer, default=0)
    successful_sends = Column(Integer, default=0)
    failed_sends = Column(Integer, default=0)
    blocked_sends = Column(Integer, default=0)

    # Конверсия
    responses_count = Column(Integer, default=0)
    dialogues_started = Column(Integer, default=0)
    conversions = Column(Integer, default=0)

    # Метаданные
    created_by = Column(String(100), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, nullable=True)

    # Связи
    lead_list = relationship("OutreachLeadList", back_populates="campaigns")
    template = relationship("OutreachTemplate", back_populates="campaigns")
    messages = relationship("OutreachMessage", back_populates="campaign", cascade="all, delete-orphan")
    session_assignments = relationship("CampaignSessionAssignment", back_populates="campaign",
                                       cascade="all, delete-orphan")


class OutreachMessage(Base, TimestampMixin):
    """Отдельное сообщение в рассылке"""
    __tablename__ = 'outreach_messages'

    id = Column(Integer, primary_key=True)

    # Связи
    campaign_id = Column(Integer, ForeignKey('outreach_campaigns.id'), nullable=False)
    lead_id = Column(Integer, ForeignKey('outreach_leads.id'), nullable=False)
    template_id = Column(Integer, ForeignKey('outreach_templates.id'), nullable=False)
    session_name = Column(String(255), nullable=False)

    # Содержание сообщения
    message_text = Column(Text, nullable=False)
    original_template_text = Column(Text, nullable=False)

    # Статус отправки
    status = Column(SQLEnum(OutreachMessageStatus), default=OutreachMessageStatus.PENDING)

    # Результат отправки
    telegram_message_id = Column(String(50), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivery_time = Column(Float, nullable=True)

    # Ошибки
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    next_retry_at = Column(DateTime, nullable=True)

    # Результат взаимодействия
    was_read = Column(Boolean, default=False)
    got_response = Column(Boolean, default=False)
    response_time = Column(Float, nullable=True)
    started_dialogue = Column(Boolean, default=False)
    converted = Column(Boolean, default=False)

    # Связи
    campaign = relationship("OutreachCampaign", back_populates="messages")
    lead = relationship("OutreachLead", back_populates="messages")
    template = relationship("OutreachTemplate", back_populates="messages")


class CampaignSessionAssignment(Base, TimestampMixin):
    """Назначение сессий на кампании"""
    __tablename__ = 'campaign_session_assignments'

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('outreach_campaigns.id'), nullable=False)
    session_name = Column(String(255), nullable=False)

    # Лимиты для этой сессии в кампании
    daily_limit = Column(Integer, nullable=False)
    current_daily_sent = Column(Integer, default=0)
    last_sent_at = Column(DateTime, nullable=True)

    # Статус сессии в кампании
    is_active = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)
    block_until = Column(DateTime, nullable=True)
    block_reason = Column(String(255), nullable=True)

    # Статистика по сессии
    total_sent = Column(Integer, default=0)
    successful_sent = Column(Integer, default=0)
    failed_sent = Column(Integer, default=0)

    # Связи
    campaign = relationship("OutreachCampaign", back_populates="session_assignments")


class SpamBlockRecord(Base, TimestampMixin):
    """Записи о спам-блокировках сессий"""
    __tablename__ = 'spam_block_records'

    id = Column(Integer, primary_key=True)
    session_name = Column(String(255), nullable=False)

    # Детали блокировки
    block_type = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=False)
    wait_seconds = Column(Integer, nullable=True)

    # Время блокировки
    blocked_at = Column(DateTime, default=datetime.utcnow)
    unblock_at = Column(DateTime, nullable=True)
    actually_unblocked_at = Column(DateTime, nullable=True)

    # Попытки восстановления
    recovery_attempted = Column(Boolean, default=False)
    recovery_successful = Column(Boolean, nullable=True)
    spambot_used = Column(Boolean, default=False)

    # Связанная кампания
    campaign_id = Column(Integer, ForeignKey('outreach_campaigns.id'), nullable=True)