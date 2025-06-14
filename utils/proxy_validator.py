# utils/proxy_validator.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
import json
import aiohttp
from typing import Dict, Set, List, Tuple
from dataclasses import dataclass
import asyncio
from loguru import logger
import time
from pathlib import Path

from config.settings.base import settings


@dataclass
class ProxyInfo:
    host: str
    port: int
    username: str = ""
    password: str = ""
    is_working: bool = True
    last_check: float = 0.0
    failures: int = 0
    response_time: float = 0.0


class ProxyValidator:
    """Валидатор прокси с детальной диагностикой"""

    def __init__(self):
        self.validated_proxies: Dict[str, ProxyInfo] = {}
        self.failed_proxies: Set[str] = set()
        self.validation_in_progress = False

    async def validate_proxy(self, host: str, port: int, username: str = "", password: str = "") -> Tuple[bool, float]:
        """Проверка работоспособности прокси с замером времени ответа"""
        try:
            proxy_key = f"{host}:{port}"

            if username and password:
                proxy_url = f"socks5://{username}:{password}@{host}:{port}"
            else:
                proxy_url = f"socks5://{host}:{port}"

            timeout = aiohttp.ClientTimeout(total=15)
            start_time = time.time()

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                        "https://httpbin.org/ip",
                        proxy=proxy_url
                ) as response:
                    response_time = time.time() - start_time

                    if response.status == 200:
                        data = await response.json()
                        origin_ip = data.get("origin", "unknown")

                        # Прокси работает
                        self.validated_proxies[proxy_key] = ProxyInfo(
                            host=host, port=port, username=username,
                            password=password, is_working=True,
                            last_check=time.time(), response_time=response_time
                        )
                        self.failed_proxies.discard(proxy_key)

                        logger.debug(f"✅ Прокси {proxy_key} работает (IP: {origin_ip}, время: {response_time:.2f}с)")
                        return True, response_time

        except asyncio.TimeoutError:
            proxy_key = f"{host}:{port}"
            self.failed_proxies.add(proxy_key)
            logger.warning(f"⏰ Прокси {proxy_key} превысил таймаут")

        except Exception as e:
            proxy_key = f"{host}:{port}"
            self.failed_proxies.add(proxy_key)
            logger.warning(f"⚠️ Прокси {proxy_key} не работает: {e}")

        return False, 0.0

    async def validate_all_from_config(self, config_path: str = None):
        """Проверка всех прокси из конфига"""
        if self.validation_in_progress:
            logger.warning("⚠️ Валидация прокси уже выполняется")
            return

        self.validation_in_progress = True

        try:
            if config_path is None:
                config_path = settings.data_dir / "proxies.json"

            if not Path(config_path).exists():
                logger.error(f"❌ Файл конфигурации прокси не найден: {config_path}")
                return

            with open(config_path, 'r') as f:
                proxy_data = json.load(f)

            logger.info(f"🔍 Начинаем валидацию {len(proxy_data)} прокси конфигураций...")

            tasks = []
            session_configs = []

            for session_name, config in proxy_data.items():
                # Берем static приоритетно, иначе dynamic
                proxy_config = config.get("static") or config.get("dynamic")

                if proxy_config and "host" in proxy_config and "port" in proxy_config:
                    task = self.validate_proxy(
                        host=proxy_config["host"],
                        port=proxy_config["port"],
                        username=proxy_config.get("username", ""),
                        password=proxy_config.get("password", "")
                    )
                    tasks.append(task)
                    session_configs.append((session_name, proxy_config))

            if not tasks:
                logger.warning("⚠️ Не найдено валидных конфигураций для проверки")
                return

            # Выполняем проверку с ограничением одновременности
            semaphore = asyncio.Semaphore(5)  # Максимум 5 одновременных проверок

            async def validate_with_semaphore(task):
                async with semaphore:
                    return await task

            results = await asyncio.gather(
                *[validate_with_semaphore(task) for task in tasks],
                return_exceptions=True
            )

            # Анализируем результаты
            working_count = 0
            failed_count = 0
            total_response_time = 0

            for i, (success, response_time) in enumerate(results):
                if isinstance(success, Exception):
                    failed_count += 1
                    session_name = session_configs[i][0]
                    logger.error(f"❌ Ошибка проверки {session_name}: {success}")
                elif success:
                    working_count += 1
                    total_response_time += response_time
                else:
                    failed_count += 1

            avg_response_time = total_response_time / working_count if working_count > 0 else 0

            logger.info(f"📊 Результаты валидации прокси:")
            logger.info(f"   ✅ Работающих: {working_count}")
            logger.info(f"   ❌ Неработающих: {failed_count}")
            if working_count > 0:
                logger.info(f"   ⏱️ Среднее время ответа: {avg_response_time:.2f}с")

            # Предупреждения
            if failed_count > 0:
                logger.warning(f"⚠️ {failed_count} прокси не работают! Проверьте конфигурацию.")

            if working_count == 0:
                logger.error(f"🚨 КРИТИЧНО: Ни один прокси не работает! Система может быть заблокирована.")

        except Exception as e:
            logger.error(f"❌ Ошибка валидации прокси: {e}")
        finally:
            self.validation_in_progress = False

    def get_validation_results(self) -> Dict[str, Dict]:
        """Получение результатов валидации"""
        results = {}

        for proxy_key, proxy_info in self.validated_proxies.items():
            results[proxy_key] = {
                "host": proxy_info.host,
                "port": proxy_info.port,
                "is_working": proxy_info.is_working,
                "response_time": proxy_info.response_time,
                "last_check": proxy_info.last_check,
                "failures": proxy_info.failures
            }

        for proxy_key in self.failed_proxies:
            if proxy_key not in results:
                host, port = proxy_key.split(":")
                results[proxy_key] = {
                    "host": host,
                    "port": int(port),
                    "is_working": False,
                    "response_time": 0.0,
                    "last_check": time.time(),
                    "failures": 1
                }

        return results

    def get_working_proxies(self) -> List[ProxyInfo]:
        """Получение списка работающих прокси"""
        return [
            proxy_info for proxy_info in self.validated_proxies.values()
            if proxy_info.is_working
        ]

    def get_failed_proxies(self) -> List[str]:
        """Получение списка неработающих прокси"""
        return list(self.failed_proxies)

    async def revalidate_failed_proxies(self):
        """Повторная проверка неработающих прокси"""
        if not self.failed_proxies:
            logger.info("✅ Нет неработающих прокси для повторной проверки")
            return

        logger.info(f"🔄 Повторная проверка {len(self.failed_proxies)} неработающих прокси")

        # Временно сохраняем список для проверки
        proxies_to_check = list(self.failed_proxies)

        tasks = []
        for proxy_key in proxies_to_check:
            host, port = proxy_key.split(":")
            task = self.validate_proxy(host, int(port))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        recovered_count = sum(1 for success, _ in results if success is True)

        if recovered_count > 0:
            logger.info(f"✅ Восстановлено {recovered_count} прокси")
        else:
            logger.info("ℹ️ Прокси остаются неработающими")


# Глобальный экземпляр
proxy_validator = ProxyValidator()