# storage/models/base.py

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum

Base = declarative_base()


class TimestampMixin:
    """Миксин для добавления временных меток"""
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ConversationStatus(str, Enum):
    """Статусы диалога"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class FunnelStage(str, Enum):
    """Этапы воронки"""
    INITIAL_CONTACT = "initial_contact"
    TRUST_BUILDING = "trust_building"
    PROJECT_INQUIRY = "project_inquiry"
    INTEREST_QUALIFICATION = "interest_qualification"
    PRESENTATION = "presentation"
    OBJECTION_HANDLING = "objection_handling"
    CONVERSION = "conversion"
    POST_CONVERSION = "post_conversion"


class MessageRole(str, Enum):
    """Роли сообщений"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class PersonaType(str, Enum):
    """Типы персон"""
    BASIC_MAN = "basic_man"
    BASIC_WOMAN = "basic_woman"
    HYIP_MAN = "hyip_man"
    HYIP_WOMAN = "hyip_woman"
    INVESTOR_MAN = "investor_man"


class SessionStatus(str, Enum):
    """Статусы сессий"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"
    ERROR = "error"


class Lead(Base, TimestampMixin):
    """Модель лида"""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, index=True)
    telegram_id = Column(String(50), unique=True, index=True, nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)

    # Аналитическая информация
    source_project = Column(String(200), nullable=True)  # Откуда пришел лид
    detected_interests = Column(JSON, default=list)  # Выявленные интересы
    risk_profile = Column(String(50), nullable=True)  # Профиль риска

    # Метаданные - изменяем название поля
    extra_data = Column(JSON, default=dict)

    # Отношения
    conversations = relationship("Conversation", back_populates="lead")
    messages = relationship("Message", back_populates="lead")


class Session(Base, TimestampMixin):
    """Модель сессии Telegram"""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    session_name = Column(String(100), unique=True, index=True)
    persona_type = Column(String(50), index=True)
    status = Column(String(20), default=SessionStatus.ACTIVE)

    # Telegram данные
    telegram_id = Column(String(50), nullable=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)

    # Настройки
    project_ref_link = Column(String(500), nullable=True)
    ai_enabled = Column(Boolean, default=True)
    proxy_config = Column(JSON, nullable=True)

    # Статистика
    total_conversations = Column(Integer, default=0)
    total_messages_sent = Column(Integer, default=0)
    total_conversions = Column(Integer, default=0)
    last_activity = Column(DateTime(timezone=True), nullable=True)

    # Отношения
    conversations = relationship("Conversation", back_populates="session")
    messages = relationship("Message", back_populates="session")


class Conversation(Base, TimestampMixin):
    """Модель диалога"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)

    # Связи
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)

    # Статус и этапы
    status = Column(String(20), default=ConversationStatus.ACTIVE)
    current_stage = Column(String(50), default=FunnelStage.INITIAL_CONTACT)

    # Флаги прогресса
    ref_link_sent = Column(Boolean, default=False)
    ref_link_sent_at = Column(DateTime(timezone=True), nullable=True)
    converted = Column(Boolean, default=False)
    converted_at = Column(DateTime(timezone=True), nullable=True)

    # Аналитика
    messages_count = Column(Integer, default=0)
    user_messages_count = Column(Integer, default=0)
    assistant_messages_count = Column(Integer, default=0)
    avg_response_time = Column(Float, default=0.0)  # секунды

    # Последняя активность
    last_user_message_at = Column(DateTime(timezone=True), nullable=True)
    last_assistant_message_at = Column(DateTime(timezone=True), nullable=True)

    # Контекст и анализ
    context_summary = Column(Text, nullable=True)  # Краткое резюме диалога
    lead_analysis = Column(JSON, default=dict)  # Анализ лида

    # Новые поля для фильтрации:
    is_whitelisted = Column(Boolean, default=False)  # Добавлен в белый список
    is_blacklisted = Column(Boolean, default=False)  # Добавлен в черный список
    auto_created = Column(Boolean, default=True)  # Создан автоматически или вручную
    requires_approval = Column(Boolean, default=False)  # Требует одобрения для ответов

    # Отношения
    lead = relationship("Lead", back_populates="conversations")
    session = relationship("Session", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")


class Message(Base, TimestampMixin):
    """Модель сообщения"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)

    # Связи
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)

    # Содержание
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)

    # Контекст сообщения
    funnel_stage = Column(String(50), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)  # секунды
    is_followup = Column(Boolean, default=False)

    # Флаги
    processed = Column(Boolean, default=False)
    requires_response = Column(Boolean, default=False)

    # AI метаданные
    ai_prompt_used = Column(Text, nullable=True)
    ai_response_raw = Column(Text, nullable=True)

    # Отношения
    conversation = relationship("Conversation", back_populates="messages")
    lead = relationship("Lead", back_populates="messages")
    session = relationship("Session", back_populates="messages")


class FollowupSchedule(Base, TimestampMixin):
    """Модель расписания фолоуапов"""
    __tablename__ = "followup_schedules"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)

    # Настройки фолоуапа
    followup_type = Column(String(50), nullable=False)  # reminder, value, proof, final
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    executed = Column(Boolean, default=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)

    # Содержание
    message_template = Column(Text, nullable=True)
    generated_message = Column(Text, nullable=True)

    # Отношения
    conversation = relationship("Conversation")


class Analytics(Base, TimestampMixin):
    """Модель аналитики"""
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True)

    # Период
    date = Column(DateTime(timezone=True), index=True)
    period_type = Column(String(20))  # hourly, daily, weekly

    # Метрики по сессиям
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)

    # Основные метрики
    total_conversations = Column(Integer, default=0)
    new_conversations = Column(Integer, default=0)
    active_conversations = Column(Integer, default=0)

    total_messages = Column(Integer, default=0)
    user_messages = Column(Integer, default=0)
    assistant_messages = Column(Integer, default=0)

    # Конверсии
    ref_links_sent = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)

    # Время ответа
    avg_response_time = Column(Float, default=0.0)
    max_response_time = Column(Float, default=0.0)

    # Дополнительные метрики
    metrics_data = Column(JSON, default=dict)

    ai_disabled = Column(Boolean, default=False)  # Отключение ИИ для конкретного диалога
    auto_responses_paused = Column(Boolean, default=False)  # Пауза автоответов

    # Отношения
    session = relationship("Session")