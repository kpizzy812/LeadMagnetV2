# 🎯 Lead Management System

Автоматизированная система для работы с лидами через Telegram, которая максимально реалистично имитирует человеческое общение и эффективно конвертирует пользователей в клиентов криптопроектов.

## ✨ Основные возможности

- 🎭 **Система персон** - реалистичные персонажи для разных типов общения
- 🔄 **Воронка продаж** - автоматическое продвижение лидов по этапам
- 🤖 **ИИ-ответы** - естественные ответы через OpenAI GPT
- 📊 **Аналитика** - детальная статистика по конверсиям и эффективности
- 📢 **Рассылки** - массовые уведомления с фильтрами
- 🛡️ **Безопасность** - человекоподобные задержки и ротация

## 🏗️ Архитектура

```
lead_system/
├── 🎯 core/                 # Ядро системы
├── 🎭 personas/             # Система персон
├── 🔄 workflows/            # Рабочие процессы
├── 🤖 bot/                  # Telegram бот управления
├── 📊 analytics/            # Система аналитики
├── 🗄️ storage/              # Модели данных
├── ⚙️ config/               # Конфигурация
```

## 🚀 Быстрый старт

### 1. Клонирование и настройка

```bash
git clone <repository-url>
cd lead_system
```

### 2. Настройка окружения

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Конфигурация

```bash
# Копирование шаблона настроек
cp .env.template .env

# Редактирование .env файла
nano .env
```

Заполните обязательные поля в `.env`:

```env
# === Database ===
DATABASE__PASSWORD=your_strong_password

# === Telegram ===
TELEGRAM__API_ID=your_api_id
TELEGRAM__API_HASH=your_api_hash
TELEGRAM__BOT_TOKEN=your_bot_token
TELEGRAM__ADMIN_IDS=[your_telegram_id]

# === OpenAI ===
OPENAI__API_KEY=sk-your-openai-api-key
```

### 4. Запуск через Docker (рекомендуется)

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f lead_management

# Остановка
docker-compose down
```

### 5. Запуск в разработке

```bash
# Запуск PostgreSQL отдельно
docker run -d \
  --name postgres \
  -e POSTGRES_DB=lead_management \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  postgres:15-alpine

# Запуск приложения
python main.py
```

## 📱 Настройка Telegram

### Получение API ключей

1. Перейдите на https://my.telegram.org
2. Войдите с вашим номером телефона
3. Создайте новое приложение
4. Скопируйте `api_id` и `api_hash`

### Создание бота управления

1. Напишите @BotFather в Telegram
2. Создайте нового бота командой `/newbot`
3. Скопируйте токен бота

### Добавление сессий

1. Поместите `.session` файлы в папку `data/sessions/`
2. Создайте подпапки по ролям: `basic_man/`, `basic_woman/`, `hyip_man/`
3. Настройте прокси в `data/proxies.json`:

```json
{
  "session_name.session": {
    "static": {
      "host": "proxy_host",
      "port": 1080,
      "username": "proxy_user",
      "password": "proxy_pass"
    }
  }
}
```

## 🎭 Настройка персон

### Доступные персоны

- **basic_man** - Простой парень, работает на обычной работе
- **basic_woman** - Простая девушка, ищет дополнительный доход
- **hyip_man** - HYIP эксперт, знает риски и способы минимизации
- **hyip_woman** - MLM женщина, активно ищет рефералов
- **investor_man** - Опытный инвестор

### Настройка проекта

Отредактируйте настройки проекта в `personas/persona_factory.py`:

```python
def setup_project():
    project = ProjectKnowledge(
        project_name="Ваш проект",
        description="Описание проекта",
        advantages=["Преимущество 1", "Преимущество 2"],
        # ... остальные настройки
    )
```

## 🤖 Использование управляющего бота

После запуска отправьте `/start` управляющему боту. Доступные функции:

- 📊 **Дашборд** - общая статистика системы
- 👥 **Сессии** - управление Telegram аккаунтами
- 💬 **Диалоги** - просмотр и управление беседами
- 📈 **Аналитика** - детальная статистика
- 📢 **Рассылки** - массовые уведомления

## ⚙️ Дополнительные настройки

### Настройка лимитов

В `.env` файле:

```env
SECURITY__MAX_MESSAGES_PER_HOUR=30
SECURITY__MAX_MESSAGES_PER_DAY=200
SECURITY__RESPONSE_DELAY_MIN=5
SECURITY__RESPONSE_DELAY_MAX=45
```

### Настройка OpenAI

```env
OPENAI__MODEL=gpt-4o-mini  # Для экономии
OPENAI__TEMPERATURE=0.85
OPENAI__MAX_TOKENS=1500
```

### Логирование

Логи сохраняются в:
- `logs/system.log` - общие логи
- `logs/errors.log` - только ошибки

## 📊 Мониторинг

### Health Check

```bash
# Проверка состояния через API
curl http://localhost:8000/health

# Проверка в Docker
docker-compose exec lead_management python -c "
import asyncio
from storage.database import db_manager
print('DB:', asyncio.run(db_manager.health_check()))
"
```

### Метрики

Основные метрики доступны в боте:
- Конверсия в лиды
- Время ответа
- Активность сессий
- Распределение по воронке

## 🔧 Разработка

### Добавление новой персоны

1. Создайте класс в `personas/base/your_persona.py`
2. Наследуйте от `BasePersona`
3. Реализуйте все абстрактные методы
4. Зарегистрируйте в `PersonaFactory`

### Добавление этапа воронки

1. Добавьте этап в `FunnelStage` enum
2. Реализуйте логику в `ConversationManager`
3. Добавьте инструкции в персоны

### Тестирование

```bash
# Запуск тестов
pytest tests/

# Только unit тесты
pytest tests/unit/

# С покрытием
pytest --cov=core tests/
```

## 🐛 Решение проблем

### Проблемы с базой данных

```bash
# Пересоздание БД
docker-compose down -v
docker-compose up -d postgres
docker-compose up lead_management
```

### Проблемы с сессиями

1. Проверьте авторизацию сессий
2. Убедитесь в корректности прокси
3. Проверьте лимиты Telegram

### Проблемы с OpenAI

1. Проверьте корректность API ключа
2. Убедитесь в наличии средств на счете
3. Проверьте лимиты запросов

## 📈 Оптимизация

### Производительность

- Используйте Redis для кэширования
- Настройте пул соединений БД
- Оптимизируйте запросы к OpenAI

### Безопасность

- Регулярно ротируйте прокси
- Мониторьте блокировки аккаунтов
- Настройте резервные стратегии

## 🤝 Поддержка

При возникновении проблем:

1. Проверьте логи в `logs/`
2. Убедитесь в корректности конфигурации
3. Проверьте состояние сервисов

## 📄 Лицензия

Проект предназначен для образовательных и коммерческих целей. Используйте ответственно и в соответствии с ToS используемых сервисов.