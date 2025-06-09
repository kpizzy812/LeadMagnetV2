#!/usr/bin/env python3
# scripts/setup_postgresql.py

"""
Скрипт для настройки PostgreSQL на разных ОС
"""

import sys
import subprocess
import platform
from pathlib import Path


def run_command(cmd, check=True, capture_output=True):
    """Выполнение команды"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr


def check_postgresql_installed():
    """Проверка установки PostgreSQL"""
    print("🔍 Проверка установки PostgreSQL...")

    # Проверяем команду psql
    success, stdout, stderr = run_command("psql --version")
    if success:
        print(f"   ✅ PostgreSQL установлен: {stdout.strip()}")
        return True
    else:
        print("   ❌ PostgreSQL не установлен")
        return False


def install_postgresql_macos():
    """Установка PostgreSQL на macOS"""
    print("🍎 Установка PostgreSQL на macOS...")

    # Проверяем Homebrew
    success, _, _ = run_command("brew --version")
    if not success:
        print("   ❌ Homebrew не установлен")
        print(
            "   💡 Установите Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
        return False

    print("   📦 Установка PostgreSQL через Homebrew...")
    success, stdout, stderr = run_command("brew install postgresql@15")

    if not success:
        print(f"   ❌ Ошибка установки: {stderr}")
        return False

    print("   ✅ PostgreSQL установлен")

    # Запускаем сервис
    print("   🚀 Запуск PostgreSQL...")
    run_command("brew services start postgresql@15")

    return True


def install_postgresql_ubuntu():
    """Установка PostgreSQL на Ubuntu/Debian"""
    print("🐧 Установка PostgreSQL на Ubuntu/Debian...")

    print("   📦 Обновление пакетов...")
    success, _, _ = run_command("sudo apt update")
    if not success:
        print("   ❌ Ошибка обновления пакетов")
        return False

    print("   📦 Установка PostgreSQL...")
    success, _, _ = run_command("sudo apt install -y postgresql postgresql-contrib")
    if not success:
        print("   ❌ Ошибка установки PostgreSQL")
        return False

    print("   🚀 Запуск PostgreSQL...")
    run_command("sudo systemctl start postgresql")
    run_command("sudo systemctl enable postgresql")

    return True


def setup_database():
    """Настройка базы данных"""
    print("🗄️ Настройка базы данных...")

    system = platform.system().lower()

    if system == "darwin":  # macOS
        # На macOS создаем пользователя с именем текущего пользователя
        import getpass
        current_user = getpass.getuser()

        print(f"   👤 Создание пользователя {current_user}...")
        run_command(f"createuser -s {current_user}", check=False)

        print("   🗄️ Создание базы данных...")
        success, _, _ = run_command("createdb lead_management")
        if success:
            print("   ✅ База данных lead_management создана")
        else:
            print("   ⚠️ База данных уже существует или ошибка создания")

        # Создаем пользователя postgres если его нет
        print("   👤 Создание пользователя postgres...")
        run_command("createuser -s postgres", check=False)

    else:  # Linux
        print("   👤 Настройка пользователя postgres...")

        # Создаем базу данных
        success, _, _ = run_command("sudo -u postgres createdb lead_management")
        if success:
            print("   ✅ База данных lead_management создана")
        else:
            print("   ⚠️ База данных уже существует")

    return True


def test_connection():
    """Тестирование подключения"""
    print("🔧 Тестирование подключения...")

    # Пробуем подключиться к базе
    cmd = "psql -d lead_management -c 'SELECT version();'"
    success, stdout, stderr = run_command(cmd)

    if success:
        print("   ✅ Подключение к базе данных успешно")
        return True
    else:
        print(f"   ❌ Ошибка подключения: {stderr}")

        # Пробуем альтернативный способ
        print("   🔄 Пробуем альтернативное подключение...")

        system = platform.system().lower()
        if system == "darwin":  # macOS
            cmd = "psql postgres -c 'CREATE DATABASE lead_management;'"
            run_command(cmd, check=False)

        return False


def update_env_file():
    """Обновление .env файла"""
    print("⚙️ Обновление .env файла...")

    base_dir = Path(__file__).parent.parent
    env_file = base_dir / ".env"

    if not env_file.exists():
        print("   ⚠️ Файл .env не найден")
        return

    # Читаем существующий файл
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Обновляем настройки БД для macOS
    system = platform.system().lower()
    if system == "darwin":  # macOS
        # Убираем пароль для локального подключения
        content = content.replace(
            "DATABASE__PASSWORD=your_postgres_password",
            "DATABASE__PASSWORD="
        )

    # Записываем обратно
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print("   ✅ Файл .env обновлен")


def main():
    """Главная функция"""

    print("🎯 Настройка PostgreSQL для Lead Management System")
    print("=" * 60)

    system = platform.system().lower()
    print(f"🖥️ Операционная система: {platform.system()}")

    try:
        # Проверяем установку
        if not check_postgresql_installed():
            if system == "darwin":  # macOS
                if not install_postgresql_macos():
                    return 1
            elif system == "linux":  # Linux
                if not install_postgresql_ubuntu():
                    return 1
            else:
                print(f"❌ Неподдерживаемая ОС: {system}")
                print("💡 Установите PostgreSQL вручную")
                return 1

        # Настраиваем базу данных
        if not setup_database():
            return 1

        # Тестируем подключение
        if not test_connection():
            print("⚠️ Подключение не удалось, но это может быть нормально")
            print("💡 Попробуйте запустить систему и посмотрите на ошибки")

        # Обновляем .env файл
        update_env_file()

        print("\n✅ Настройка PostgreSQL завершена!")
        print("\n🎯 Следующие шаги:")
        print("1. Проверьте подключение: python scripts/quick_start.py")
        print("2. Если есть ошибки - проверьте логи PostgreSQL")
        print("3. Запустите систему: python main.py")

        return 0

    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
        return 1
    except Exception as e:
        print(f"\n💥 Ошибка: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())