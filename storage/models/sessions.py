# storage/models/sessions.py - Модели сессий С ДОБАВЛЕННЫМ PersonaType

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum

from .base import Base, TimestampMixin


class SessionStatus(Enum):
    """Статусы сессий"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    MAINTENANCE = "maintenance"


# ДОБАВЛЯЕМ PersonaType enum!
class PersonaType(Enum):
    """Типы персон"""
    BASIC_MAN = "basic_man"
    BASIC_WOMAN = "basic_woman"
    HYIP_MAN = "hyip_man"
    HYIP_WOMAN = "hyip_woman"
    INVESTOR_MAN = "investor_man"


class Session(Base, TimestampMixin):
    """Модель сессии Telegram"""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    session_name = Column(String(100), unique=True, index=True, nullable=False)
    persona_type = Column(String(50), index=True)
    status = Column(String(20), default=SessionStatus.ACTIVE.value, nullable=False)

    # Telegram данные
    telegram_id = Column(String(50), nullable=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)

    # Настройки
    project_ref_link = Column(String(500), nullable=True)
    ai_enabled = Column(Boolean, default=True, nullable=False)
    proxy_config = Column(JSON, nullable=True)

    # Статистика
    total_conversations = Column(Integer, default=0, nullable=False)
    total_messages_sent = Column(Integer, default=0, nullable=False)
    total_conversions = Column(Integer, default=0, nullable=False)
    last_activity = Column(DateTime, default=func.now(), nullable=True)
    last_error = Column(String(500), nullable=True)

    # Связи
    conversations = relationship("Conversation", back_populates="session")
    messages = relationship("Message", back_populates="session")

    # Индексы
    __table_args__ = (
        Index('idx_session_status_ai', 'status', 'ai_enabled'),
        Index('idx_session_activity', 'last_activity'),
        Index('idx_session_persona', 'persona_type', 'status'),
    )

    @property
    def is_active(self) -> bool:
        """Проверка активности сессии"""
        return self.status == SessionStatus.ACTIVE.value and self.ai_enabled

    def __repr__(self):
        return f"<Session {self.session_name} ({self.status})>"


# НОВЫЕ модели для ретроспективной системы

class RetrospectiveScanState(Base, TimestampMixin):
    """Состояние ретроспективного сканирования"""
    __tablename__ = "retrospective_scan_states"

    id = Column(Integer, primary_key=True)
    session_name = Column(String(100), nullable=False, unique=True, index=True)

    # Статистика сканирования
    last_scan_timestamp = Column(DateTime, nullable=True)
    last_successful_scan = Column(DateTime, nullable=True)
    last_error_timestamp = Column(DateTime, nullable=True)
    last_error_message = Column(String(1000), nullable=True)

    # Счетчики
    total_scans = Column(Integer, default=0, nullable=False)
    successful_scans = Column(Integer, default=0, nullable=False)
    failed_scans = Column(Integer, default=0, nullable=False)
    total_messages_found = Column(Integer, default=0, nullable=False)

    # Настройки
    is_enabled = Column(Boolean, default=True, nullable=False)
    scan_interval_override = Column(Integer, nullable=True)  # Персональный интервал для сессии

    # Индексы
    __table_args__ = (
        Index('idx_scan_state_enabled', 'is_enabled', 'last_scan_timestamp'),
        Index('idx_scan_state_session', 'session_name'),
    )

    def __repr__(self):
        return f"<ScanState {self.session_name} (scans: {self.total_scans})>"


class ScanLog(Base, TimestampMixin):
    """Лог ретроспективного сканирования"""
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True)
    session_name = Column(String(100), nullable=False, index=True)

    # Результат сканирования
    scan_timestamp = Column(DateTime, default=func.now(), nullable=False, index=True)
    success = Column(Boolean, nullable=False, index=True)
    duration_seconds = Column(Integer, nullable=False)

    # Статистика
    dialogs_scanned = Column(Integer, default=0, nullable=False)
    new_messages_found = Column(Integer, default=0, nullable=False)
    messages_processed = Column(Integer, default=0, nullable=False)

    # Ошибки
    error_count = Column(Integer, default=0, nullable=False)
    error_details = Column(String(2000), nullable=True)

    # Дополнительные данные
    metadata = Column(JSON, nullable=True)  # JSON с деталями сканирования

    # Индексы для аналитики
    __table_args__ = (
        Index('idx_scan_log_session_time', 'session_name', 'scan_timestamp'),
        Index('idx_scan_log_success', 'success', 'scan_timestamp'),
        Index('idx_scan_log_performance', 'session_name', 'duration_seconds'),
    )

    def __repr__(self):
        status = "✅" if self.success else "❌"
        return f"<ScanLog {self.session_name} {status} ({self.new_messages_found} msgs)>"