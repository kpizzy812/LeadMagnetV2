# config/settings/base.py

from pathlib import Path
from typing import List, Optional, Dict, Any
# from pydantic import BaseSettings, validator
from pydantic_settings import BaseSettings as PydanticBaseSettings
import os
from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
SESSIONS_DIR = DATA_DIR / "sessions"
DIALOGS_DIR = DATA_DIR / "dialogs"

# Создание необходимых директорий
for dir_path in [DATA_DIR, LOGS_DIR, SESSIONS_DIR, DIALOGS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


class DatabaseSettings(PydanticBaseSettings):
    """Настройки базы данных"""
    host: str = "localhost"
    port: int = 5432
    name: str = "lead_management"
    user: str = "postgres"
    password: str = ""

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    class Config:
        env_prefix = "DATABASE__"


class TelegramSettings(PydanticBaseSettings):
    """Настройки Telegram"""
    api_id: int = 0
    api_hash: str = ""
    bot_token: str = ""
    admin_ids: List[int] = []

    class Config:
        env_prefix = "TELEGRAM__"


class OpenAISettings(PydanticBaseSettings):
    """Настройки OpenAI"""
    api_key: str = ""
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
    session_check_interval: int = 30  # секунды
    analytics_update_interval: int = 300  # секунды

    class Config:
        env_prefix = "SYSTEM__"


class Settings(PydanticBaseSettings):
    """Главные настройки приложения"""

    # Подсистемы - создаем только если .env файл существует
    database: DatabaseSettings = DatabaseSettings()
    telegram: TelegramSettings = TelegramSettings()
    openai: OpenAISettings = OpenAISettings()
    security: SecuritySettings = SecuritySettings()
    system: SystemSettings = SystemSettings()

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

    class Config:
        case_sensitive = False
        env_file = ".env"
        env_nested_delimiter = "__"


# Глобальный экземпляр настроек
try:
    settings = Settings()
except Exception as e:
    # Если ошибка загрузки настроек, создаем с дефолтными значениями
    print(f"⚠️ Предупреждение: не удалось загрузить настройки ({e})")
    print("💡 Проверьте наличие файла .env")
    settings = Settings(
        database=DatabaseSettings(),
        telegram=TelegramSettings(),
        openai=OpenAISettings(),
        security=SecuritySettings(),
        system=SystemSettings()
    )

# Настройка логирования только если настройки загружены
from loguru import logger
import sys

logger.remove()
logger.add(
    sys.stdout,
    level=settings.system.log_level,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# Добавляем файловое логирование только если папка существует
if settings.logs_dir.exists():
    logger.add(
        settings.logs_dir / "system.log",
        level="INFO",
        rotation="1 day",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    logger.add(
        settings.logs_dir / "errors.log",
        level="ERROR",
        rotation="1 week",
        retention="1 month",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )