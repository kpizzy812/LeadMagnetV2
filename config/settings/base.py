# config/settings/base.py - ОБНОВЛЕННАЯ ВЕРСИЯ

from pathlib import Path
from typing import List, Optional
from pydantic import BaseSettings as PydanticBaseSettings, validator
import os

# Определяем пути
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
SESSIONS_DIR = DATA_DIR / "sessions"
DIALOGS_DIR = DATA_DIR / "dialogs"

# Создаем необходимые папки
for dir_path in [DATA_DIR, LOGS_DIR, SESSIONS_DIR, DIALOGS_DIR]:
    dir_path.mkdir(exist_ok=True)


class DatabaseSettings(PydanticBaseSettings):
    """Настройки базы данных"""
    host: str = "localhost"
    port: int = 5432
    name: str = "lead_management"
    user: str = "postgres"
    password: str = "your_postgres_password"

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    class Config:
        env_prefix = "DATABASE__"


class TelegramSettings(PydanticBaseSettings):
    """Настройки Telegram"""
    api_id: int = 0
    api_hash: str = "your_api_hash"
    bot_token: str = "your_bot_token"
    admin_ids: List[int] = [123456789]

    @validator('admin_ids', pre=True)
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            # Парсим строку вида "[123, 456]" или "123,456"
            v = v.strip('[]')
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v

    class Config:
        env_prefix = "TELEGRAM__"


class OpenAISettings(PydanticBaseSettings):
    """Настройки OpenAI"""
    api_key: str = "sk-your-openai-api-key"
    model: str = "gpt-4o-mini"
    max_tokens: int = 1500
    temperature: float = 0.85

    class Config:
        env_prefix = "OPENAI__"


class SecuritySettings(PydanticBaseSettings):
    """Настройки безопасности"""
    max_messages_per_hour: int = 30
    max_messages_per_day: int = 200
    response_delay_min: int = 5
    response_delay_max: int = 45
    proxy_rotation_interval: int = 3600  # секунды

    class Config:
        env_prefix = "SECURITY__"


class SystemSettings(PydanticBaseSettings):
    """Системные настройки"""
    debug: bool = False
    log_level: str = "INFO"
    max_concurrent_sessions: int = 10
    session_check_interval: int = 30  # секунды (УСТАРЕЛО в новой системе)
    analytics_update_interval: int = 300  # секунды

    # НОВЫЕ настройки для ретроспективной системы
    retrospective_scan_interval: int = 120  # секунды (по умолчанию 2 минуты)
    max_parallel_session_scans: int = 3  # максимум одновременных сканирований
    message_scan_limit: int = 50  # лимит сообщений для сканирования на диалог

    # Настройки одобрения сообщений
    auto_approve_cold_outreach_dialogs: bool = True  # автоматически одобрять диалоги из cold outreach
    require_admin_approval_for_new_dialogs: bool = True  # требовать одобрение для новых диалогов

    class Config:
        env_prefix = "SYSTEM__"


class ColdOutreachSettings(PydanticBaseSettings):
    """Настройки холодной рассылки"""
    enabled: bool = True
    max_daily_messages_per_session: int = 100
    messages_per_hour_limit: int = 20
    delay_between_messages_min: int = 30  # секунды
    delay_between_messages_max: int = 180  # секунды

    # Настройки безопасности
    stop_on_flood_wait: bool = True
    auto_recovery_enabled: bool = True
    session_rotation_on_limits: bool = True

    class Config:
        env_prefix = "COLD_OUTREACH__"


class Settings(PydanticBaseSettings):
    """Главные настройки приложения"""

    # Подсистемы - создаем только если .env файл существует
    database: DatabaseSettings = DatabaseSettings()
    telegram: TelegramSettings = TelegramSettings()
    openai: OpenAISettings = OpenAISettings()
    security: SecuritySettings = SecuritySettings()
    system: SystemSettings = SystemSettings()
    cold_outreach: ColdOutreachSettings = ColdOutreachSettings()

    # Пути
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    logs_dir: Path = LOGS_DIR
    sessions_dir: Path = SESSIONS_DIR
    dialogs_dir: Path = DIALOGS_DIR

    def __init__(self, **kwargs):
        # Проверяем существование .env файла
        env_file = BASE_DIR / ".env"
        if not env_file.exists():
            # Если .env не существует, используем значения по умолчанию
            super().__init__(**kwargs)
        else:
            # Если .env существует, загружаем из него
            super().__init__(_env_file=str(env_file), **kwargs)

    @property
    def is_development(self) -> bool:
        return self.system.debug

    @property
    def is_production(self) -> bool:
        return not self.system.debug

    class Config:
        case_sensitive = False
        env_file_encoding = 'utf-8'


# Создаем глобальный экземпляр настроек
settings = Settings()