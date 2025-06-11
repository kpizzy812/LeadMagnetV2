"""
Модели базы данных для системы холодной рассылки (Cold Outreach)
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from typing import Optional, Dict, Any, List

from .base import BaseModel


class CampaignStatus(enum.Enum):
    """Статусы кампании рассылки"""
    DRAFT = "draft"  # Черновик
    ACTIVE = "active"  # Активная
    PAUSED = "paused"  # Приостановлена
    COMPLETED = "completed"  # Завершена
    FAILED = "failed"  # Провалена (критическая ошибка)


class OutreachMessageStatus(enum.Enum):
    """Статусы отправки сообщений"""
    PENDING = "pending"  # Ожидает отправки
    SENDING = "sending"  # В процессе отправки
    SENT = "sent"  # Отправлено успешно
    FAILED = "failed"  # Не удалось отправить
    BLOCKED = "blocked"  # Заблокировано (privacy)
    FLOOD_WAIT = "flood_wait"  # Ожидание после флуд-ошибки
    TOO_MANY_REQUESTS = "too_many_requests"  # Слишком много запросов


class LeadList(BaseModel):
    """Список лидов для рассылки"""
    __tablename__ = 'lead_lists'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Статистика списка
    total_leads = Column(Integer, default=0)
    processed_leads = Column(Integer, default=0)
    successful_sends = Column(Integer, default=0)
    failed_sends = Column(Integer, default=0)

    # Метаданные
    source = Column(String(255), nullable=True)  # Откуда получен список
    tags = Column(JSON, default=list)  # Теги для группировки
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    leads = relationship("Lead", back_populates="lead_list", cascade="all, delete-orphan")
    campaigns = relationship("OutreachCampaign", back_populates="lead_list")


class Lead(BaseModel):
    """Отдельный лид в списке"""
    __tablename__ = 'leads'

    id = Column(Integer, primary_key=True)
    lead_list_id = Column(Integer, ForeignKey('lead_lists.id'), nullable=False)

    # Данные лида
    username = Column(String(100), nullable=False)  # @username без @
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    full_name = Column(String(500), nullable=True)

    # Telegram метаданные
    user_id = Column(String(50), nullable=True)  # Telegram ID если известен
    is_premium = Column(Boolean, nullable=True)  # Премиум статус
    last_seen = Column(DateTime, nullable=True)  # Последняя активность

    # Статус обработки
    is_processed = Column(Boolean, default=False)
    last_contact_attempt = Column(DateTime, nullable=True)
    successful_contacts = Column(Integer, default=0)
    failed_contacts = Column(Integer, default=0)

    # Блокировки и ошибки
    is_blocked = Column(Boolean, default=False)  # Заблокирован для рассылки
    block_reason = Column(String(255), nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    lead_list = relationship("LeadList", back_populates="leads")
    messages = relationship("OutreachMessage", back_populates="lead")


class OutreachTemplate(BaseModel):
    """Шаблон сообщения для рассылки"""
    __tablename__ = 'outreach_templates'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Содержание шаблона
    text = Column(Text, nullable=False)
    variables = Column(JSON, default=list)  # Список переменных типа {first_name}

    # Настройки персонализации
    persona_type = Column(String(50), nullable=True)  # basic_man, basic_woman, etc
    category = Column(String(100), nullable=True)  # crypto, investment, etc

    # Статистика эффективности
    usage_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)
    avg_response_time = Column(Float, nullable=True)  # Среднее время ответа в часах

    # ИИ настройки
    enable_ai_uniquification = Column(Boolean, default=False)
    uniquification_level = Column(String(20), default="medium")  # light, medium, heavy

    # Метаданные
    is_active = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)  # Admin username

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    campaigns = relationship("OutreachCampaign", back_populates="template")
    messages = relationship("OutreachMessage", back_populates="template")


class OutreachCampaign(BaseModel):
    """Кампания холодной рассылки"""
    __tablename__ = 'outreach_campaigns'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Связи с другими моделями
    lead_list_id = Column(Integer, ForeignKey('lead_lists.id'), nullable=False)
    template_id = Column(Integer, ForeignKey('outreach_templates.id'), nullable=False)

    # Статус и настройки
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT)

    # Настройки рассылки
    max_messages_per_day = Column(Integer, default=50)  # Общий лимит кампании
    delay_between_messages = Column(Integer, default=1800)  # Секунды между сообщениями
    use_premium_sessions_only = Column(Boolean, default=False)
    enable_spambot_recovery = Column(Boolean, default=True)

    # Временные ограничения
    start_time = Column(DateTime, nullable=True)  # Время начала рассылки
    end_time = Column(DateTime, nullable=True)  # Время окончания
    daily_start_hour = Column(Integer, default=10)  # Час начала в день (10:00)
    daily_end_hour = Column(Integer, default=18)  # Час окончания в день (18:00)

    # Прогресс и статистика
    total_targets = Column(Integer, default=0)  # Всего целей
    processed_targets = Column(Integer, default=0)  # Обработано
    successful_sends = Column(Integer, default=0)  # Успешно отправлено
    failed_sends = Column(Integer, default=0)  # Неудачи
    blocked_sends = Column(Integer, default=0)  # Заблокировано

    # Конверсия
    responses_count = Column(Integer, default=0)  # Количество ответов
    dialogues_started = Column(Integer, default=0)  # Диалоги начаты
    conversions = Column(Integer, default=0)  # Конверсии (реф ссылки)

    # Метаданные
    created_by = Column(String(100), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    lead_list = relationship("LeadList", back_populates="campaigns")
    template = relationship("OutreachTemplate", back_populates="campaigns")
    messages = relationship("OutreachMessage", back_populates="campaign", cascade="all, delete-orphan")
    session_assignments = relationship("CampaignSessionAssignment", back_populates="campaign",
                                       cascade="all, delete-orphan")


class OutreachMessage(BaseModel):
    """Отдельное сообщение в рассылке"""
    __tablename__ = 'outreach_messages'

    id = Column(Integer, primary_key=True)

    # Связи
    campaign_id = Column(Integer, ForeignKey('outreach_campaigns.id'), nullable=False)
    lead_id = Column(Integer, ForeignKey('leads.id'), nullable=False)
    template_id = Column(Integer, ForeignKey('outreach_templates.id'), nullable=False)
    session_name = Column(String(255), nullable=False)  # Сессия которая отправляла

    # Содержание сообщения
    message_text = Column(Text, nullable=False)  # Финальный текст (после обработки переменных)
    original_template_text = Column(Text, nullable=False)  # Оригинальный шаблон

    # Статус отправки
    status = Column(SQLEnum(OutreachMessageStatus), default=OutreachMessageStatus.PENDING)

    # Результат отправки
    telegram_message_id = Column(String(50), nullable=True)  # ID сообщения в Telegram
    sent_at = Column(DateTime, nullable=True)
    delivery_time = Column(Float, nullable=True)  # Время доставки в секундах

    # Ошибки
    error_code = Column(String(100), nullable=True)  # Код ошибки
    error_message = Column(Text, nullable=True)  # Описание ошибки
    retry_count = Column(Integer, default=0)  # Количество попыток
    next_retry_at = Column(DateTime, nullable=True)  # Время следующей попытки

    # Результат взаимодействия
    was_read = Column(Boolean, default=False)  # Прочитано ли
    got_response = Column(Boolean, default=False)  # Был ли ответ
    response_time = Column(Float, nullable=True)  # Время ответа в часах
    started_dialogue = Column(Boolean, default=False)  # Перешло ли в диалог
    converted = Column(Boolean, default=False)  # Была ли конверсия

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    campaign = relationship("OutreachCampaign", back_populates="messages")
    lead = relationship("Lead", back_populates="messages")
    template = relationship("OutreachTemplate", back_populates="messages")


class CampaignSessionAssignment(BaseModel):
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
    is_blocked = Column(Boolean, default=False)  # Временно заблокирована
    block_until = Column(DateTime, nullable=True)  # До какого времени заблокирована
    block_reason = Column(String(255), nullable=True)

    # Статистика по сессии
    total_sent = Column(Integer, default=0)
    successful_sent = Column(Integer, default=0)
    failed_sent = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    campaign = relationship("OutreachCampaign", back_populates="session_assignments")


class SpamBlockRecord(BaseModel):
    """Записи о спам-блокировках сессий"""
    __tablename__ = 'spam_block_records'

    id = Column(Integer, primary_key=True)
    session_name = Column(String(255), nullable=False)

    # Детали блокировки
    block_type = Column(String(50), nullable=False)  # flood_wait, too_many_requests, etc
    error_message = Column(Text, nullable=False)
    wait_seconds = Column(Integer, nullable=True)  # Время ожидания в секундах

    # Время блокировки
    blocked_at = Column(DateTime, default=datetime.utcnow)
    unblock_at = Column(DateTime, nullable=True)  # Расчетное время разблокировки
    actually_unblocked_at = Column(DateTime, nullable=True)  # Фактическое время

    # Попытки восстановления
    recovery_attempted = Column(Boolean, default=False)
    recovery_successful = Column(Boolean, nullable=True)
    spambot_used = Column(Boolean, default=False)

    # Связанная кампания (если блокировка во время рассылки)
    campaign_id = Column(Integer, ForeignKey('outreach_campaigns.id'), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)