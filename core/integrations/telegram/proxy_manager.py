# core/integrations/telegram/proxy_manager.py
import json
import socks
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from loguru import logger
from config.settings.base import settings


@dataclass
class ProxyConfig:
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    proxy_type: str = "socks5"


class ProxyManager:
    """ИСПРАВЛЕННЫЙ менеджер прокси с полной валидацией"""

    def __init__(self):
        self.proxies: Dict[str, Dict] = {}
        self.proxy_validation_cache: Dict[str, bool] = {}
        self._load_proxies()

    def _load_proxies(self):
        """Загрузка прокси из конфигурации с валидацией"""
        proxy_file = settings.data_dir / "proxies.json"
        if proxy_file.exists():
            try:
                with open(proxy_file, 'r', encoding='utf-8') as f:
                    self.proxies = json.load(f)
                logger.info(f"📡 Загружено {len(self.proxies)} прокси конфигураций")

                # Валидируем конфигурацию
                self._validate_proxy_config()

            except Exception as e:
                logger.error(f"❌ Ошибка загрузки прокси: {e}")
        else:
            logger.warning("⚠️ Файл proxies.json не найден! Создайте его для безопасности.")

    def _validate_proxy_config(self):
        """Валидация конфигурации прокси"""
        session_files = list(settings.sessions_dir.rglob("*.session"))

        missing_proxies = []
        invalid_configs = []
        valid_configs = []

        for session_file in session_files:
            session_name = session_file.stem
            session_key = f"{session_name}.session"

            if session_key not in self.proxies:
                missing_proxies.append(session_name)
                continue

            session_config = self.proxies[session_key]

            has_static = "static" in session_config
            has_dynamic = "dynamic" in session_config

            if not (has_static or has_dynamic):
                invalid_configs.append(f"{session_name} (нет static/dynamic)")
                continue

            config_valid = False
            if has_static:
                static_config = session_config["static"]
                if "host" in static_config and "port" in static_config:
                    config_valid = True

            if not config_valid and has_dynamic:
                dynamic_config = session_config["dynamic"]
                if "host" in dynamic_config and "port" in dynamic_config:
                    config_valid = True

            if config_valid:
                valid_configs.append(session_name)
            else:
                invalid_configs.append(f"{session_name} (нет host/port)")

        # Логируем результаты валидации
        if valid_configs:
            logger.success(
                f"✅ Валидные прокси ({len(valid_configs)}): {', '.join(valid_configs[:5])}{'...' if len(valid_configs) > 5 else ''}")

        if missing_proxies:
            logger.error(
                f"🚫 Сессии БЕЗ прокси ({len(missing_proxies)}): {', '.join(missing_proxies[:5])}{'...' if len(missing_proxies) > 5 else ''}")

        if invalid_configs:
            logger.error(
                f"❌ Некорректные конфигурации ({len(invalid_configs)}): {', '.join(invalid_configs[:3])}{'...' if len(invalid_configs) > 3 else ''}")

    def get_proxy_for_session(self, session_name: str) -> Optional[tuple]:
        """Получение прокси для сессии"""
        session_key = f"{session_name}.session"
        session_config = self.proxies.get(session_key, {})

        if not session_config:
            logger.error(f"🚫 КРИТИЧНО: Прокси для {session_name} НЕ НАЙДЕН!")
            return None

        # Приоритет: static, потом dynamic
        proxy_config = session_config.get("static") or session_config.get("dynamic")

        if not proxy_config:
            logger.error(f"❌ Конфигурация прокси для {session_name} пуста!")
            return None

        # Проверяем обязательные поля
        required_fields = ["host", "port"]
        for field in required_fields:
            if field not in proxy_config:
                logger.error(f"❌ В прокси для {session_name} отсутствует поле '{field}'!")
                return None

        logger.debug(f"📡 Прокси для {session_name}: {proxy_config['host']}:{proxy_config['port']}")

        return (
            socks.SOCKS5,
            proxy_config["host"],
            proxy_config["port"],
            True,  # requires_auth
            proxy_config.get("username"),
            proxy_config.get("password")
        )

    def get_proxy_config(self, session_name: str) -> Optional[ProxyConfig]:
        """Получение конфигурации прокси как объекта"""
        session_key = f"{session_name}.session"
        session_config = self.proxies.get(session_key, {})

        if not session_config:
            return None

        proxy_config = session_config.get("static") or session_config.get("dynamic")
        if not proxy_config:
            return None

        return ProxyConfig(
            host=proxy_config["host"],
            port=proxy_config["port"],
            username=proxy_config.get("username"),
            password=proxy_config.get("password")
        )

    def enforce_proxy_requirement(self, session_name: str) -> bool:
        """СТРОГАЯ проверка: есть ли валидный прокси для сессии"""
        proxy = self.get_proxy_for_session(session_name)

        if not proxy:
            logger.error(f"🚫 БЛОКИРОВКА: Сессия {session_name} не может быть создана без прокси!")
            return False

        return True

    def get_all_session_proxy_status(self) -> Dict[str, Dict[str, Any]]:
        """Получение статуса прокси для всех сессий"""
        session_files = list(settings.sessions_dir.rglob("*.session"))
        results = {}

        for session_file in session_files:
            session_name = session_file.stem
            results[session_name] = self.validate_session_proxy(session_name)

        return results

    def validate_session_proxy(self, session_name: str) -> Dict[str, Any]:
        """Детальная валидация прокси для сессии"""
        session_key = f"{session_name}.session"

        result = {
            "session_name": session_name,
            "session_key": session_key,
            "has_config": False,
            "has_static": False,
            "has_dynamic": False,
            "static_valid": False,
            "dynamic_valid": False,
            "proxy_info": None,
            "errors": []
        }

        if session_key not in self.proxies:
            result["errors"].append(f"Отсутствует ключ '{session_key}' в proxies.json")
            return result

        result["has_config"] = True
        session_config = self.proxies[session_key]

        # Проверяем static конфигурацию
        if "static" in session_config:
            result["has_static"] = True
            static_config = session_config["static"]

            required_fields = ["host", "port"]
            missing_fields = [f for f in required_fields if f not in static_config]

            if not missing_fields:
                result["static_valid"] = True
                result["proxy_info"] = f"{static_config['host']}:{static_config['port']} (static)"
            else:
                result["errors"].append(f"Static: отсутствуют поля {missing_fields}")

        # Проверяем dynamic конфигурацию
        if "dynamic" in session_config:
            result["has_dynamic"] = True
            dynamic_config = session_config["dynamic"]

            required_fields = ["host", "port"]
            missing_fields = [f for f in required_fields if f not in dynamic_config]

            if not missing_fields:
                result["dynamic_valid"] = True
                if not result["proxy_info"]:  # Если static не валиден
                    result["proxy_info"] = f"{dynamic_config['host']}:{dynamic_config['port']} (dynamic)"
            else:
                result["errors"].append(f"Dynamic: отсутствуют поля {missing_fields}")

        return result