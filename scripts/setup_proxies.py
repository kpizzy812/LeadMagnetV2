#!/usr/bin/env python3
# scripts/setup_proxies.py

"""
Скрипт для настройки прокси для сессий
"""

import json
import sys
from pathlib import Path


def setup_proxies():
    """Настройка прокси"""

    base_dir = Path(__file__).parent.parent
    sessions_dir = base_dir / "data" / "sessions"
    proxy_file = base_dir / "data" / "proxies.json"

    print("🌐 Настройка прокси для Telegram сессий")
    print("=" * 50)

    # Находим все сессии
    session_files = list(sessions_dir.rglob("*.session"))

    if not session_files:
        print("❌ Не найдено session файлов")
        return False

    print(f"📁 Найдено {len(session_files)} session файлов")

    choice = input(
        "\nВыберите опцию:\n1. Создать пустой файл прокси (работа без прокси)\n2. Настроить прокси для всех сессий\n3. Отмена\n\nВаш выбор (1-3): ")

    if choice == "1":
        # Создаем пустой файл
        with open(proxy_file, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)

        print("✅ Создан пустой файл прокси")
        print("⚠️ Внимание: сессии будут работать без прокси (менее безопасно)")
        return True

    elif choice == "2":
        # Настраиваем прокси
        proxies = {}

        print("\n📝 Введите данные SOCKS5 прокси:")
        print("💡 Для пропуска сессии просто нажмите Enter\n")

        proxy_host = input("Хост прокси (например proxy.example.com): ")
        if not proxy_host:
            print("❌ Хост прокси обязателен")
            return False

        proxy_port = input("Порт прокси (например 1080): ")
        if not proxy_port:
            print("❌ Порт прокси обязателен")
            return False

        proxy_user = input("Пользователь прокси: ")
        proxy_pass = input("Пароль прокси: ")

        # Настраиваем для всех сессий один прокси
        use_same = input(f"\nИспользовать этот прокси для всех {len(session_files)} сессий? (yes/no): ").lower()

        if use_same in ['yes', 'y', 'да', 'д']:
            for session_file in session_files:
                session_name = session_file.name
                proxies[session_name] = {
                    "static": {
                        "host": proxy_host,
                        "port": int(proxy_port),
                        "username": proxy_user,
                        "password": proxy_pass
                    }
                }
        else:
            # Настраиваем индивидуально (упрощенно - используем тот же прокси)
            for session_file in session_files[:5]:  # Первые 5
                session_name = session_file.name
                use_proxy = input(f"Настроить прокси для {session_name}? (yes/no): ").lower()

                if use_proxy in ['yes', 'y', 'да', 'д']:
                    proxies[session_name] = {
                        "static": {
                            "host": proxy_host,
                            "port": int(proxy_port),
                            "username": proxy_user,
                            "password": proxy_pass
                        }
                    }

        # Сохраняем файл
        with open(proxy_file, 'w', encoding='utf-8') as f:
            json.dump(proxies, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Настроено прокси для {len(proxies)} сессий")
        print(f"📁 Файл сохранен: {proxy_file}")
        return True

    else:
        print("❌ Отменено")
        return False


def main():
    try:
        success = setup_proxies()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
        return 1
    except Exception as e:
        print(f"\n💥 Ошибка: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())