#!/usr/bin/env python3
# scripts/quick_start.py

"""
Скрипт быстрого запуска и проверки системы
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings.base import settings
from storage.database import db_manager
from core.integrations.openai_client import openai_client
from core.integrations.telegram_client import telegram_session_manager
from loguru import logger
import json


class QuickStartChecker:
    """Проверка готовности системы к запуску"""

    def __init__(self):
        self.checks_passed = 0
        self.total_checks = 8

    async def run_all_checks(self):
        """Запуск всех проверок"""

        print("🔍 Проверка готовности Lead Management System к запуску...\n")

        # Проверки
        await self.check_env_file()
        await self.check_database()
        await self.check_openai()
        await self.check_telegram_settings()
        await self.check_directories()
        await self.check_sessions()
        await self.check_proxies()
        await self.check_permissions()

        # Результат
        print(f"\n📊 Результат: {self.checks_passed}/{self.total_checks} проверок пройдено")

        if self.checks_passed == self.total_checks:
            print("✅ Система готова к запуску!")
            print("\n🚀 Для запуска выполните: python main.py")
            return True
        else:
            print("❌ Система НЕ готова к запуску!")
            print("💡 Исправьте указанные проблемы и повторите проверку")
            return False

    async def check_env_file(self):
        """Проверка .env файла"""

        print("1️⃣ Проверка файла .env...")

        env_file = settings.base_dir / ".env"
        if not env_file.exists():
            print("   ❌ Файл .env не найден")
            print("   💡 Выполните: cp .env.template .env")
            print("   💡 Затем заполните обязательные переменные")
            return

        # Проверяем обязательные переменные
        required_vars = {
            "TELEGRAM__API_ID": settings.telegram.api_id,
            "TELEGRAM__API_HASH": settings.telegram.api_hash,
            "TELEGRAM__BOT_TOKEN": settings.telegram.bot_token,
            "OPENAI__API_KEY": settings.openai.api_key,
            "DATABASE__PASSWORD": settings.database.password
        }

        missing_vars = []
        for var_name, value in required_vars.items():
            # Проверяем что значение не пустое и не дефолтное
            if (not value or
                    str(value).startswith("your_") or
                    str(value) in ["0", "", "sk-your-openai-api-key"]):
                missing_vars.append(var_name)

        if missing_vars:
            print(f"   ❌ Не заполнены переменные: {', '.join(missing_vars)}")
            print("   💡 Отредактируйте .env файл и заполните эти переменные")
            return

        print("   ✅ Файл .env корректный")
        self.checks_passed += 1

    async def check_database(self):
        """Проверка подключения к базе данных"""

        print("2️⃣ Проверка базы данных...")

        try:
            await db_manager.initialize()
            is_healthy = await db_manager.health_check()

            if is_healthy:
                print("   ✅ База данных подключена")
                self.checks_passed += 1
            else:
                print("   ❌ Проблемы с базой данных")
                print("   💡 Проверьте что PostgreSQL запущен и настройки подключения корректны")

            await db_manager.close()

        except Exception as e:
            print(f"   ❌ Ошибка подключения к БД: {e}")
            print("   💡 Убедитесь что PostgreSQL запущен")

    async def check_openai(self):
        """Проверка OpenAI API"""

        print("3️⃣ Проверка OpenAI API...")

        try:
            test_result = await openai_client.test_connection()

            if test_result["success"]:
                print(f"   ✅ OpenAI API работает (модель: {test_result['model']})")
                print(f"   ⏱️ Время ответа: {test_result['processing_time']}с")
                self.checks_passed += 1
            else:
                print(f"   ❌ Ошибка OpenAI API: {test_result['error']}")
                print("   💡 Проверьте API ключ и наличие средств на счете")

        except Exception as e:
            print(f"   ❌ Ошибка тестирования OpenAI: {e}")

    async def check_telegram_settings(self):
        """Проверка настроек Telegram"""

        print("4️⃣ Проверка настроек Telegram...")

        try:
            # Проверяем что admin_ids не пустой
            if not settings.telegram.admin_ids:
                print("   ❌ Не указаны TELEGRAM__ADMIN_IDS")
                print("   💡 Добавьте свой Telegram ID в настройки")
                return

            # Проверяем формат токена бота
            bot_token = settings.telegram.bot_token
            if not bot_token or ":" not in bot_token:
                print("   ❌ Некорректный TELEGRAM__BOT_TOKEN")
                print("   💡 Получите токен у @BotFather")
                return

            print("   ✅ Настройки Telegram корректны")
            print(f"   👥 Админов: {len(settings.telegram.admin_ids)}")
            self.checks_passed += 1

        except Exception as e:
            print(f"   ❌ Ошибка проверки Telegram: {e}")

    async def check_directories(self):
        """Проверка директорий"""

        print("5️⃣ Проверка директорий...")

        required_dirs = [
            settings.data_dir,
            settings.logs_dir,
            settings.sessions_dir,
            settings.dialogs_dir
        ]

        missing_dirs = []
        for directory in required_dirs:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                missing_dirs.append(str(directory))

        if missing_dirs:
            print(f"   ⚙️ Созданы директории: {', '.join(missing_dirs)}")

        print("   ✅ Все директории готовы")
        self.checks_passed += 1

    async def check_sessions(self):
        """Проверка сессий"""

        print("6️⃣ Проверка Telegram сессий...")

        session_files = list(settings.sessions_dir.rglob("*.session"))

        if not session_files:
            print("   ⚠️ Не найдено .session файлов")
            print("   💡 Добавьте .session файлы в папку data/sessions/")
            print("   💡 Или используйте: python scripts/session_manager.py create")
            return

        print(f"   📁 Найдено {len(session_files)} session файлов")

        # Проверяем первые 3 сессии
        await telegram_session_manager.initialize()

        authorized_count = 0
        for session_file in session_files[:3]:
            session_name = session_file.stem
            is_auth = await telegram_session_manager._check_session_auth(session_file)

            if is_auth:
                authorized_count += 1
                print(f"   ✅ {session_name} - авторизована")
            else:
                print(f"   ❌ {session_name} - НЕ авторизована")

        if authorized_count > 0:
            print(f"   ✅ {authorized_count} сессий готовы к работе")
            self.checks_passed += 1
        else:
            print("   ❌ Нет авторизованных сессий")
            print("   💡 Пересоздайте сессии с правильными учетными данными")

    async def check_proxies(self):
        """Проверка конфигурации прокси"""

        print("7️⃣ Проверка прокси...")

        proxy_file = settings.data_dir / "proxies.json"

        if not proxy_file.exists():
            print("   ⚠️ Файл proxies.json не найден")
            print("   💡 Создайте файл по примеру data/proxies.json.example")
            print("   💡 Или работайте без прокси (менее безопасно)")
            self.checks_passed += 1  # Прокси не обязательны
            return

        try:
            with open(proxy_file, 'r', encoding='utf-8') as f:
                proxies = json.load(f)

            if not proxies:
                print("   ⚠️ Файл proxies.json пустой")
            else:
                print(f"   ✅ Настроено {len(proxies)} прокси")

                # Показываем первые 3
                for i, (session_name, config) in enumerate(list(proxies.items())[:3]):
                    proxy_info = config.get("static", {})
                    host = proxy_info.get("host", "unknown")
                    port = proxy_info.get("port", "unknown")
                    print(f"   📡 {session_name}: {host}:{port}")

            self.checks_passed += 1

        except json.JSONDecodeError:
            print("   ❌ Ошибка формата proxies.json")
            print("   💡 Проверьте синтаксис JSON")
        except Exception as e:
            print(f"   ❌ Ошибка чтения proxies.json: {e}")

    async def check_permissions(self):
        """Проверка прав доступа"""

        print("8️⃣ Проверка прав доступа...")

        try:
            # Проверяем запись в папку логов
            test_log_file = settings.logs_dir / "test.tmp"
            test_log_file.write_text("test")
            test_log_file.unlink()

            # Проверяем запись в папку данных
            test_data_file = settings.data_dir / "test.tmp"
            test_data_file.write_text("test")
            test_data_file.unlink()

            print("   ✅ Права доступа в порядке")
            self.checks_passed += 1

        except Exception as e:
            print(f"   ❌ Проблемы с правами доступа: {e}")
            print("   💡 Убедитесь что папки доступны для записи")


async def main():
    """Главная функция"""

    checker = QuickStartChecker()

    try:
        success = await checker.run_all_checks()

        if success:
            print("\n🎯 Дополнительные команды:")
            print("   • python scripts/session_manager.py list - список сессий")
            print("   • python scripts/session_manager.py create <name> <phone> - создать сессию")
            print("   • python main.py - запуск системы")

            return 0
        else:
            return 1

    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
        return 1
    except Exception as e:
        print(f"\n💥 Ошибка проверки: {e}")
        return 1


if __name__ == "__main__":
    print("🎯 Lead Management System - Проверка готовности")
    print("=" * 60)

    exit_code = asyncio.run(main())
    sys.exit(exit_code)