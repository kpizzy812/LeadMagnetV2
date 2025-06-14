# utils/startup_optimizer.py - НОВЫЙ компонент для ускорения запуска

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Optional, Set
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from loguru import logger
from config.settings.base import settings


@dataclass
class SessionStartupInfo:
    session_name: str
    is_valid: bool
    has_proxy: bool
    validation_time: float
    error: Optional[str] = None
    proxy_info: Optional[str] = None


class StartupOptimizer:
    """Оптимизатор запуска системы - быстрая валидация и параллельная инициализация"""

    def __init__(self):
        self.cache_file = settings.data_dir / "startup_cache.json"
        self.startup_cache: Dict[str, Dict] = {}
        self.validation_semaphore = asyncio.Semaphore(10)  # Максимум 10 одновременных проверок
        self.startup_stats = {
            "total_sessions": 0,
            "validated_sessions": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "failed_sessions": 0,
            "startup_time": 0.0
        }

    async def fast_startup_validation(self) -> Tuple[List[SessionStartupInfo], Dict]:
        """Быстрая валидация всех сессий с кэшированием и параллельностью"""
        start_time = time.time()

        logger.info("🚀 Запуск быстрой валидации сессий...")

        # Загружаем кэш
        await self._load_startup_cache()

        # Сканируем файлы сессий
        session_files = list(settings.sessions_dir.rglob("*.session"))
        self.startup_stats["total_sessions"] = len(session_files)

        if not session_files:
            logger.warning("⚠️ Не найдено файлов сессий")
            return [], self.startup_stats

        # Группируем сессии для оптимизации
        cached_sessions, validation_needed = await self._categorize_sessions(session_files)

        # Результаты
        results: List[SessionStartupInfo] = []

        # Добавляем кэшированные результаты
        results.extend(cached_sessions)
        self.startup_stats["cache_hits"] = len(cached_sessions)

        # Параллельная валидация новых/измененных сессий
        if validation_needed:
            logger.info(f"🔍 Валидация {len(validation_needed)} сессий...")

            # Создаем задачи валидации с ограничением параллельности
            validation_tasks = [
                self._validate_session_fast(session_file)
                for session_file in validation_needed
            ]

            # Выполняем валидацию батчами
            validated_results = await self._run_validation_batches(validation_tasks)
            results.extend(validated_results)

        # Обновляем кэш
        await self._update_startup_cache(results)

        # Финальная статистика
        self.startup_stats["validated_sessions"] = len([r for r in results if r.is_valid])
        self.startup_stats["failed_sessions"] = len([r for r in results if not r.is_valid])
        self.startup_stats["cache_misses"] = len(validation_needed)
        self.startup_stats["startup_time"] = time.time() - start_time

        # Логируем результаты
        await self._log_startup_results(results)

        return results, self.startup_stats

    async def _categorize_sessions(self, session_files: List[Path]) -> Tuple[List[SessionStartupInfo], List[Path]]:
        """Разделение сессий на кэшированные и требующие валидации"""
        cached_sessions = []
        validation_needed = []

        for session_file in session_files:
            session_name = session_file.stem

            # Проверяем кэш
            if await self._is_cache_valid(session_file):
                # Восстанавливаем из кэша
                cache_data = self.startup_cache[session_name]
                cached_sessions.append(SessionStartupInfo(
                    session_name=session_name,
                    is_valid=cache_data["is_valid"],
                    has_proxy=cache_data["has_proxy"],
                    validation_time=0.0,  # Из кэша
                    proxy_info=cache_data.get("proxy_info")
                ))
            else:
                validation_needed.append(session_file)

        return cached_sessions, validation_needed

    async def _is_cache_valid(self, session_file: Path) -> bool:
        """Проверка валидности кэша для сессии"""
        session_name = session_file.stem

        if session_name not in self.startup_cache:
            return False

        cache_data = self.startup_cache[session_name]

        # Проверяем время жизни кэша (1 час)
        cache_time = datetime.fromisoformat(cache_data["cached_at"])
        if datetime.now() - cache_time > timedelta(hours=1):
            return False

        # Проверяем что файл не изменился
        file_mtime = session_file.stat().st_mtime
        if file_mtime != cache_data["file_mtime"]:
            return False

        return True

    async def _validate_session_fast(self, session_file: Path) -> SessionStartupInfo:
        """Быстрая валидация одной сессии с тайм-аутом"""
        session_name = session_file.stem
        start_time = time.time()

        async with self.validation_semaphore:
            try:
                # Проверяем прокси первым делом
                proxy_info = await self._check_session_proxy(session_name)
                if not proxy_info["has_proxy"]:
                    return SessionStartupInfo(
                        session_name=session_name,
                        is_valid=False,
                        has_proxy=False,
                        validation_time=time.time() - start_time,
                        error="No proxy configured"
                    )

                # Быстрая проверка файла сессии без полного подключения
                is_valid = await self._quick_session_check(session_file, proxy_info["proxy_tuple"])

                return SessionStartupInfo(
                    session_name=session_name,
                    is_valid=is_valid,
                    has_proxy=True,
                    validation_time=time.time() - start_time,
                    proxy_info=proxy_info["proxy_string"]
                )

            except Exception as e:
                return SessionStartupInfo(
                    session_name=session_name,
                    is_valid=False,
                    has_proxy=False,
                    validation_time=time.time() - start_time,
                    error=str(e)
                )

    async def _check_session_proxy(self, session_name: str) -> Dict:
        """Быстрая проверка конфигурации прокси"""
        try:
            from core.integrations.telegram.proxy_manager import ProxyManager
            proxy_manager = ProxyManager()

            proxy_tuple = proxy_manager.get_proxy_for_session(session_name)
            if not proxy_tuple:
                return {"has_proxy": False, "proxy_tuple": None, "proxy_string": None}

            proxy_string = f"{proxy_tuple[1]}:{proxy_tuple[2]}"
            return {
                "has_proxy": True,
                "proxy_tuple": proxy_tuple,
                "proxy_string": proxy_string
            }

        except Exception as e:
            logger.error(f"❌ Ошибка проверки прокси для {session_name}: {e}")
            return {"has_proxy": False, "proxy_tuple": None, "proxy_string": None}

    async def _quick_session_check(self, session_file: Path, proxy_tuple: tuple) -> bool:
        """Максимально быстрая проверка валидности сессии"""
        try:
            # Используем более короткий таймаут для быстрой проверки
            from telethon import TelegramClient

            temp_client = TelegramClient(
                str(session_file),
                api_id=settings.telegram.api_id,
                api_hash=settings.telegram.api_hash,
                proxy=proxy_tuple,
                timeout=5,  # Короткий таймаут
                connection_retries=1,  # Одна попытка
                auto_reconnect=False
            )

            # Быстрая проверка с таймаутом
            try:
                await asyncio.wait_for(temp_client.connect(), timeout=10)
                is_authorized = await asyncio.wait_for(temp_client.is_user_authorized(), timeout=5)

                await temp_client.disconnect()
                await asyncio.sleep(0.1)  # Короткая пауза

                return is_authorized

            except asyncio.TimeoutError:
                logger.debug(f"⏰ Таймаут проверки сессии {session_file.stem}")
                try:
                    await temp_client.disconnect()
                except:
                    pass
                return False

        except Exception as e:
            logger.debug(f"❌ Ошибка быстрой проверки {session_file.stem}: {e}")
            return False

    async def _run_validation_batches(self, validation_tasks: List) -> List[SessionStartupInfo]:
        """Выполнение валидации батчами для оптимизации"""
        results = []
        batch_size = 5  # Размер батча

        for i in range(0, len(validation_tasks), batch_size):
            batch = validation_tasks[i:i + batch_size]

            logger.info(
                f"🔄 Валидация батча {i // batch_size + 1}/{(len(validation_tasks) + batch_size - 1) // batch_size}")

            try:
                batch_results = await asyncio.gather(*batch, return_exceptions=True)

                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error(f"❌ Ошибка в батче валидации: {result}")
                    else:
                        results.append(result)

                # Короткая пауза между батчами
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"❌ Ошибка выполнения батча валидации: {e}")

        return results

    async def _load_startup_cache(self):
        """Загрузка кэша запуска"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.startup_cache = json.load(f)
                logger.debug(f"📁 Загружен кэш запуска: {len(self.startup_cache)} записей")
            else:
                self.startup_cache = {}
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки кэша: {e}")
            self.startup_cache = {}

    async def _update_startup_cache(self, results: List[SessionStartupInfo]):
        """Обновление кэша запуска"""
        try:
            # Обновляем кэш новыми результатами
            for result in results:
                if result.validation_time > 0:  # Только валидированные, не из кэша
                    session_file = settings.sessions_dir / f"{result.session_name}.session"

                    self.startup_cache[result.session_name] = {
                        "is_valid": result.is_valid,
                        "has_proxy": result.has_proxy,
                        "proxy_info": result.proxy_info,
                        "validation_time": result.validation_time,
                        "cached_at": datetime.now().isoformat(),
                        "file_mtime": session_file.stat().st_mtime if session_file.exists() else 0,
                        "error": result.error
                    }

            # Сохраняем кэш
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.startup_cache, f, indent=2, ensure_ascii=False)

            logger.debug(f"💾 Кэш запуска обновлен: {len(self.startup_cache)} записей")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления кэша: {e}")

    async def _log_startup_results(self, results: List[SessionStartupInfo]):
        """Логирование результатов запуска"""
        valid_sessions = [r for r in results if r.is_valid]
        invalid_sessions = [r for r in results if not r.is_valid]

        # Группируем по типам ошибок
        error_groups = {}
        for result in invalid_sessions:
            error_type = result.error or "Unknown error"
            if error_type not in error_groups:
                error_groups[error_type] = []
            error_groups[error_type].append(result.session_name)

        # Красивый вывод результатов
        logger.info("📊 Результаты быстрой валидации:")
        logger.info(f"   ✅ Валидных сессий: {len(valid_sessions)}")
        logger.info(f"   ❌ Невалидных сессий: {len(invalid_sessions)}")
        logger.info(f"   🚀 Время валидации: {self.startup_stats['startup_time']:.2f}с")
        logger.info(f"   📁 Использован кэш: {self.startup_stats['cache_hits']}")
        logger.info(f"   🔍 Проверено заново: {self.startup_stats['cache_misses']}")

        # Подробности по валидным сессиям (первые 10)
        if valid_sessions:
            display_sessions = valid_sessions[:10]
            session_names = [s.session_name for s in display_sessions]
            more_text = f" и еще {len(valid_sessions) - 10}" if len(valid_sessions) > 10 else ""
            logger.success(f"✅ Готовые сессии: {', '.join(session_names)}{more_text}")

        # Подробности по ошибкам
        if error_groups:
            logger.warning("⚠️ Обнаружены проблемы:")
            for error_type, sessions in error_groups.items():
                display_sessions = sessions[:3]
                more_text = f" и еще {len(sessions) - 3}" if len(sessions) > 3 else ""
                logger.warning(f"   {error_type}: {', '.join(display_sessions)}{more_text}")

    async def clear_cache(self):
        """Очистка кэша запуска"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
            self.startup_cache = {}
            logger.info("🧹 Кэш запуска очищен")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша: {e}")

    def get_startup_stats(self) -> Dict:
        """Получение статистики запуска"""
        return self.startup_stats.copy()


# Глобальный экземпляр
startup_optimizer = StartupOptimizer()