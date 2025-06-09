# storage/database.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config.settings.base import settings
from storage.models.base import Base
from loguru import logger
import asyncio


class DatabaseManager:
    """Менеджер базы данных"""

    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Инициализация базы данных"""
        try:
            # Создание движка
            self.engine = create_async_engine(
                settings.database.url,
                echo=settings.system.debug,
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600,
            )

            # Создание фабрики сессий
            self.session_factory = sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Создание таблиц
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("✅ База данных инициализирована")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise

    async def close(self):
        """Закрытие соединения с базой данных"""
        if self.engine:
            await self.engine.dispose()
            logger.info("🔒 Соединение с БД закрыто")

    def get_session(self) -> AsyncSession:
        """Получение сессии базы данных"""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")
        return self.session_factory()

    async def health_check(self) -> bool:
        """Проверка здоровья базы данных"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"❌ Health check БД провален: {e}")
            return False


# Глобальный экземпляр менеджера БД
db_manager = DatabaseManager()


async def get_db_session() -> AsyncSession:
    """Dependency для получения сессии БД"""
    async with db_manager.get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class DatabaseConnection:
    """Контекстный менеджер для работы с БД"""

    def __init__(self):
        self.session = None

    async def __aenter__(self) -> AsyncSession:
        self.session = db_manager.get_session()
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()


# Удобная функция для получения соединения
def get_db() -> DatabaseConnection:
    """Получение соединения с базой данных"""
    return DatabaseConnection()