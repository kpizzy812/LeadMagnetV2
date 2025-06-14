import json
import aiohttp
from typing import Dict, Set
from dataclasses import dataclass
import asyncio
from loguru import logger
import time

@dataclass
class ProxyInfo:
    host: str
    port: int
    username: str = ""
    password: str = ""
    is_working: bool = True
    last_check: float = 0.0
    failures: int = 0


class ProxyValidator:
    """Валидатор прокси - добавляем к существующему proxy manager"""

    def __init__(self):
        self.validated_proxies: Dict[str, ProxyInfo] = {}
        self.failed_proxies: Set[str] = set()

    async def validate_proxy(self, host: str, port: int, username: str = "", password: str = "") -> bool:
        """Проверка работоспособности прокси"""
        try:
            proxy_key = f"{host}:{port}"

            if username and password:
                proxy_url = f"socks5://{username}:{password}@{host}:{port}"
            else:
                proxy_url = f"socks5://{host}:{port}"

            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                        "https://httpbin.org/ip",
                        proxy=proxy_url
                ) as response:
                    if response.status == 200:
                        # Прокси работает
                        self.validated_proxies[proxy_key] = ProxyInfo(
                            host=host, port=port, username=username,
                            password=password, is_working=True,
                            last_check=time.time()
                        )
                        self.failed_proxies.discard(proxy_key)
                        logger.debug(f"✅ Прокси {proxy_key} работает")
                        return True

        except Exception as e:
            proxy_key = f"{host}:{port}"
            self.failed_proxies.add(proxy_key)
            logger.warning(f"⚠️ Прокси {proxy_key} не работает: {e}")

        return False

    async def validate_all_from_config(self, config_path: str = "data/proxies.json"):
        """Проверка всех прокси из конфига"""
        try:
            with open(config_path, 'r') as f:
                proxy_data = json.load(f)

            tasks = []
            for session_name, config in proxy_data.items():
                if "static" in config:
                    proxy_config = config["static"]
                    task = self.validate_proxy(
                        host=proxy_config["host"],
                        port=proxy_config["port"],
                        username=proxy_config.get("username", ""),
                        password=proxy_config.get("password", "")
                    )
                    tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            working_count = sum(1 for r in results if r is True)
            logger.info(f"✅ Работает прокси: {working_count}/{len(tasks)}")

        except Exception as e:
            logger.error(f"❌ Ошибка валидации прокси: {e}")


# Глобальный экземпляр
proxy_validator = ProxyValidator()