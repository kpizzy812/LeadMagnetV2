#!/bin/bash
# setup_git.sh - Скрипт для быстрой настройки Git

echo "🚀 Настройка Git репозитория для Lead Management System"

# Проверяем что мы в правильной папке
if [ ! -f "main.py" ]; then
    echo "❌ Ошибка: Запустите скрипт в корне проекта (там где main.py)"
    exit 1
fi

# Инициализация Git
echo "📁 Инициализация Git..."
git init

# Добавление remote
echo "🔗 Добавление удаленного репозитория..."
git remote add origin https://github.com/kpizzy812/LeadMagnetV2.git

# Создание структуры папок
echo "📂 Создание структуры папок..."
mkdir -p data/sessions data/dialogs data/logs tmp
touch data/sessions/.gitkeep
touch data/dialogs/.gitkeep
touch data/logs/.gitkeep
touch tmp/.gitkeep

# Создание .env.template если его нет
if [ ! -f ".env.template" ]; then
    echo "⚙️ Создание .env.template..."
    cat > .env.template << 'EOF'
# === Database Settings ===
DATABASE__HOST=localhost
DATABASE__PORT=5432
DATABASE__NAME=lead_management
DATABASE__USER=postgres
DATABASE__PASSWORD=your_postgres_password

# === Telegram Settings ===
TELEGRAM__API_ID=your_api_id
TELEGRAM__API_HASH=your_api_hash
TELEGRAM__BOT_TOKEN=your_bot_token
TELEGRAM__ADMIN_IDS=[123456789]

# === OpenAI Settings ===
OPENAI__API_KEY=sk-your-openai-api-key
OPENAI__MODEL=gpt-4o-mini
OPENAI__MAX_TOKENS=1500
OPENAI__TEMPERATURE=0.85

# === Security Settings ===
SECURITY__MAX_MESSAGES_PER_HOUR=30
SECURITY__MAX_MESSAGES_PER_DAY=200
SECURITY__RESPONSE_DELAY_MIN=5
SECURITY__RESPONSE_DELAY_MAX=45

# === System Settings ===
SYSTEM__DEBUG=false
SYSTEM__LOG_LEVEL=INFO
SYSTEM__MAX_CONCURRENT_SESSIONS=10
EOF
fi

# Добавление файлов
echo "📦 Добавление файлов в Git..."
git add .

# Первый коммит
echo "💾 Создание первого коммита..."
git commit -m "🎯 Initial commit: Lead Management System MVP

✅ Модульная архитектура
✅ Система персон (basic_man, basic_woman, hyip_man)
✅ Воронка продаж (8 этапов)
✅ OpenAI интеграция
✅ PostgreSQL модели
✅ Telegram бот управления
✅ Аналитика и метрики
✅ Docker развертывание
✅ Готово к production"

# Отправка в GitHub
echo "🚀 Отправка в GitHub..."
git branch -M main
git push -u origin main

echo ""
echo "✅ Готово! Репозиторий настроен и загружен в GitHub"
echo "🌐 Ссылка: https://github.com/kpizzy812/LeadMagnetV2"
echo ""
echo "📋 Следующие шаги:"
echo "1. Скопируйте .env.template в .env"
echo "2. Заполните настройки в .env файле"
echo "3. Добавьте .session файлы в data/sessions/"
echo "4. Настройте прокси в data/proxies.json"
echo "5. Запустите: python main.py"
echo ""
echo "🤝 Для работы с Git:"
echo "• git add . && git commit -m \"Описание\" && git push"
echo "• git pull (получить обновления)"
echo "• git status (проверить состояние)"