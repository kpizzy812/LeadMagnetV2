# 🎯 Lead Management System - Полное руководство пользователя

## 📋 Содержание

1. [Введение](#введение)
2. [Быстрый старт](#быстрый-старт)
3. [Установка и настройка](#установка-и-настройка)
4. [Управление сессиями](#управление-сессиями)
5. [Персоны и проекты](#персоны-и-проекты)
6. [Telegram бот управления](#telegram-бот-управления)
7. [Аналитика и мониторинг](#аналитика-и-мониторинг)
8. [Диагностика и исправление проблем](#диагностика-и-исправление-проблем)
9. [Скрипты автоматизации](#скрипты-автоматизации)
10. [Развертывание](#развертывание)
11. [Часто задаваемые вопросы](#часто-задаваемые-вопросы)

---

## 📖 Введение

Lead Management System - это автоматизированная система для работы с лидами через Telegram, которая максимально реалистично имитирует человеческое общение и эффективно конвертирует пользователей в клиентов криптопроектов.

### ✨ Основные возможности

- 🎭 **5 типов персон** для разных аудиторий
- 🔄 **8-этапная воронка продаж** с автоматическим продвижением
- 🤖 **ИИ-ответы** через OpenAI GPT-4
- 📊 **Полная аналитика** конверсий и эффективности
- 📢 **Массовые рассылки** с фильтрами
- 📅 **Система фолоуапов** для "холодных" лидов
- 🛡️ **Безопасность** с человекоподобными задержками
- 🔗 **Прокси поддержка** для всех сессий

---

## 🚀 Быстрый старт

### 1. Проверка готовности системы

```bash
# Полная проверка всех компонентов
python scripts/quick_start.py
```

**Что проверяется:**
- ✅ Файл .env и обязательные переменные
- ✅ Подключение к PostgreSQL
- ✅ OpenAI API ключ и лимиты
- ✅ Настройки Telegram
- ✅ Структура папок
- ✅ Авторизация сессий
- ✅ Конфигурация прокси
- ✅ Права доступа к файлам

### 2. Запуск системы

```bash
# Запуск основной системы
python main.py
```

### 3. Доступ к управлению

После запуска отправьте `/start` управляющему боту в Telegram.

---

## ⚙️ Установка и настройка

### Первоначальная настройка

#### 1. Создание .env файла

```bash
# Копирование шаблона
cp .env.template .env

# Редактирование настроек
nano .env  # или любой другой редактор
```

#### 2. Обязательные настройки в .env

```env
# === Database ===
DATABASE__PASSWORD=ваш_сильный_пароль

# === Telegram ===
TELEGRAM__API_ID=ваш_api_id          # Получить на https://my.telegram.org
TELEGRAM__API_HASH=ваш_api_hash      # Получить на https://my.telegram.org
TELEGRAM__BOT_TOKEN=токен_бота       # Получить у @BotFather
TELEGRAM__ADMIN_IDS=[ваш_telegram_id] # Узнать у @userinfobot

# === OpenAI ===
OPENAI__API_KEY=sk-ваш-ключ         # API ключ OpenAI
```

#### 3. Настройка базы данных

```bash
# Автоматическая настройка PostgreSQL
python scripts/setup_postgresql.py

# Или вручную (Ubuntu/Debian):
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres createdb lead_management

# macOS (Homebrew):
brew install postgresql@15
brew services start postgresql@15
createdb lead_management
```

#### 4. Исправление схемы БД (если нужно)

```bash
# Добавление недостающих колонок (безопасно)
python scripts/fix_database.py
# Выберите опцию 1

# Полное пересоздание таблиц (удалит данные!)
python scripts/fix_database.py
# Выберите опцию 2
```

---

## 👥 Управление сессиями

### Основные команды управления сессиями

#### Создание новой сессии

```bash
# Создание сессии без прокси
python scripts/session_manager.py create имя_сессии +1234567890 basic_man

# Создание сессии с прокси
python scripts/session_manager.py create имя_сессии +1234567890 basic_woman '{"host":"proxy.com","port":1080,"username":"user","password":"pass"}'
```

**Параметры:**
- `имя_сессии` - уникальное имя (например: alex_crypto)
- `+1234567890` - номер телефона с кодом страны
- `basic_man` - тип персоны (см. раздел Персоны)
- JSON прокси - опционально для безопасности

#### Просмотр всех сессий

```bash
# Список всех сессий с подробной информацией
python scripts/session_manager.py list
```

**Показывает:**
- ✅/❌ Статус авторизации
- 💾 Наличие в базе данных
- 🤖/📴 Статус ИИ
- 🎭 Назначенная персона
- @username пользователя

#### Управление персонами

```bash
# Установка персоны для сессии
python scripts/session_manager.py persona имя_сессии basic_woman

# Доступные персоны:
# basic_man     - Простой парень
# basic_woman   - Простая девушка
# hyip_man      - HYIP эксперт
# hyip_woman    - HYIP женщина (в разработке)
# investor_man  - Опытный инвестор (в разработке)
```

#### Установка реферальных ссылок

```bash
# Установка реф ссылки для сессии
python scripts/session_manager.py reflink имя_сессии "https://t.me/bot?start=ref123"

# Массовая установка для всех сессий
python scripts/set_ref_links.py

# Просмотр текущих ссылок
python scripts/set_ref_links.py show
```

#### Проверка авторизации

```bash
# Проверка авторизации всех сессий
python scripts/session_manager.py check

# Проверка статуса сессий в БД
python scripts/check_sessions.py
```

#### Удаление сессии

```bash
# Удаление сессии (с подтверждением)
python scripts/session_manager.py delete имя_сессии
```

### Настройка прокси

#### Автоматическая настройка

```bash
# Интерактивная настройка прокси
python scripts/setup_proxies.py
```

#### Ручная настройка

Создайте файл `data/proxies.json`:

```json
{
  "session1.session": {
    "static": {
      "host": "proxy.example.com",
      "port": 1080,
      "username": "proxy_user",
      "password": "proxy_pass"
    }
  }
}
```

---

## 🎭 Персоны и проекты

### Доступные персоны

#### 1. Basic Man (basic_man)
**Профиль:** Простой парень, 25-35 лет, работает на обычной работе
**Стиль:** Дружелюбный, простой, без заумных терминов
**История:** Раньше не верил в инвест проекты, но попробовал и получается
**Подходит для:** Обычных пользователей, новичков в инвестициях

#### 2. Basic Woman (basic_woman)  
**Профиль:** Обычная девушка, 23-32 лет, ищет дополнительный доход
**Стиль:** Эмоциональный, много эмодзи, женственный
**История:** Боялась инвестиций, но подруга посоветовала попробовать
**Подходит для:** Женской аудитории, осторожных инвесторов

#### 3. HYIP Man (hyip_man)
**Профиль:** Опытный инвестор, 28-40 лет, знает все о хайпах
**Стиль:** Профессиональный, использует термины, фокус на фактах
**История:** Многолетний опыт, умеет минимизировать риски
**Подходит для:** Опытных инвесторов, профессиональной аудитории

### Настройка проекта

Отредактируйте файл `personas/persona_factory.py`, функцию `setup_default_project()`:

```python
your_project = ProjectKnowledge(
    project_name="Название вашего проекта",
    description="Краткое описание проекта",
    advantages=[
        "Преимущество 1",
        "Преимущество 2", 
        "Преимущество 3"
    ],
    support_contact="@ваша_поддержка",
    minimum_investment="от $10"
)
```

---

## 🤖 Telegram бот управления

### Основное меню

После `/start` доступны разделы:

#### 📊 Дашборд
- Общая статистика системы
- Активные диалоги и сессии
- Сообщения и конверсии за сегодня
- Обновление в реальном времени

#### 👥 Сессии
- Список всех Telegram аккаунтов
- Управление ИИ (вкл/выкл)
- Настройка персон
- Просмотр диалогов сессии

#### 💬 Диалоги
- Все активные беседы
- История переписки
- Ручная отправка сообщений
- Управление фильтрами

#### 📈 Аналитика
- **По сессиям** - эффективность аккаунтов
- **По персонам** - какие персоны лучше конвертят
- **Воронка** - распределение по этапам
- **Времени** - анализ времени ответов
- **За период** - статистика за дни/недели

#### 📢 Рассылки
- **Всем лидам** - массовая рассылка
- **По сессии** - через конкретный аккаунт
- **По статусу** - с/без реф ссылки
- **По персоне** - определенному типу лидов

#### 📅 Фолоуапы
- Ожидающие напоминания
- Статистика по типам фолоуапов
- Отмена запланированных

#### 🤖 Управление ИИ
- **Глобальное** - вся система вкл/выкл
- **По сессиям** - управление аккаунтами
- **По диалогам** - отдельные беседы
- **Массовые операции** - пауза/возобновление

### Управление диалогами

#### Просмотр диалога
- Полная информация о лиде
- Статистика сообщений
- Текущий этап воронки
- История переписки

#### Ручная отправка
1. Выберите диалог
2. Нажмите "✏️ Написать"
3. Введите текст сообщения
4. Подтвердите отправку

#### Фильтрация диалогов
- **Белый список** - автоматические ответы
- **Черный список** - игнорировать
- **Ожидают одобрения** - требуют проверки

---

## 📊 Аналитика и мониторинг

### Встроенная аналитика (через бота)

#### Основные метрики
- Общая конверсия в %
- Активные диалоги
- Сообщения за 24ч
- Время ответа системы

#### По сессиям
- Топ аккаунтов по конверсиям
- Сообщения и диалоги по каждой сессии
- Эффективность персон

#### Воронка продаж
```
🤝 Первый контакт     → 23%
🤗 Построение доверия → 18%
❓ Выяснение проектов → 15%
🎯 Квалификация      → 12%
📢 Презентация       → 8%
🛡️ Работа с возражениями → 5%
💰 Конверсия         → 3%
✅ После конверсии   → 2%
```

### Скрипты мониторинга

#### Мониторинг в реальном времени

```bash
# Постоянный мониторинг (обновление каждые 5 сек)
python scripts/monitor_sessions.py realtime

# Показывает:
# 🕐 12:34:56 | Активных: 5 | Очередь: 2
# 🟢 session1 | Диалогов: 12 | Сообщений: 45
```

#### Статус системы

```bash
# Полный обзор состояния
python scripts/monitor_sessions.py status

# Экспорт статистики в JSON
python scripts/monitor_sessions.py export
```

#### Статистика реф ссылок

```bash
# Конверсии по агентам
python scripts/check_ref_stats.py

# Показывает:
# 🤖 session1 (basic_man)
#    💬 Всего диалогов: 15
#    🔗 Реф ссылок: 3
#    📈 Конверсия: 20%
```

---

## 🔧 Диагностика и исправление проблем

### Автоматическая диагностика

#### Полная диагностика системы

```bash
# Найти и исправить ВСЕ проблемы
python scripts/fix_sessions.py full

# Проверяет и исправляет:
# ✅ Отключенные сессии
# ✅ Неавторизованные аккаунты  
# ✅ Переполнение очереди
# ✅ Устаревшие задержки
# ✅ Несоответствия в БД
```

#### Конкретные проблемы

```bash
# Переподключить отвалившиеся сессии
python scripts/fix_sessions.py disconnected

# Проверить авторизацию
python scripts/fix_sessions.py unauthorized

# Найти неактивные сессии
python scripts/fix_sessions.py inactive

# Очистить очередь сообщений
python scripts/fix_sessions.py queue

# Очистить старые задержки
python scripts/fix_sessions.py delays

# Исправить БД
python scripts/fix_sessions.py database
```

#### Исправление диалогов

```bash
# Обработать необработанные сообщения
python scripts/fix_dialogs.py
```

### Ручная диагностика

#### Проверка компонентов

```bash
# Тест всех компонентов
python scripts/test_system.py

# Тест только OpenAI
python scripts/test_openai.py
```

### Типичные проблемы и решения

#### ❌ "База данных недоступна"
```bash
# Проверить статус PostgreSQL
sudo systemctl status postgresql

# Перезапустить если нужно
sudo systemctl restart postgresql

# Проверить подключение
python scripts/quick_start.py
```

#### ❌ "OpenAI API не работает"
```bash
# Проверить ключ
python scripts/test_openai.py

# Возможные причины:
# - Неверный API ключ
# - Нет средств на счете
# - Превышены лимиты
```

#### ❌ "Сессии не авторизованы"
```bash
# Проверить все сессии
python scripts/session_manager.py check

# Пересоздать проблемную сессию
python scripts/session_manager.py delete old_session
python scripts/session_manager.py create new_session +phone persona
```

#### ❌ "Очередь переполнена"
```bash
# Перезапуск очищает очередь
python main.py

# Или принудительная очистка
python scripts/fix_sessions.py queue
```

---

## 🛠️ Скрипты автоматизации

### Управление сессиями

| Команда | Описание | Пример |
|---------|----------|---------|
| `session_manager.py create` | Создать сессию | `python scripts/session_manager.py create alex +123456 basic_man` |
| `session_manager.py list` | Список сессий | `python scripts/session_manager.py list` |
| `session_manager.py delete` | Удалить сессию | `python scripts/session_manager.py delete alex` |
| `session_manager.py persona` | Сменить персону | `python scripts/session_manager.py persona alex basic_woman` |
| `session_manager.py reflink` | Установить ссылку | `python scripts/session_manager.py reflink alex "https://t.me/bot?start=ref"` |
| `session_manager.py check` | Проверить авторизацию | `python scripts/session_manager.py check` |

### Мониторинг и диагностика

| Команда | Описание | Пример |
|---------|----------|---------|
| `quick_start.py` | Полная проверка | `python scripts/quick_start.py` |
| `monitor_sessions.py status` | Статус системы | `python scripts/monitor_sessions.py status` |
| `monitor_sessions.py realtime` | Мониторинг онлайн | `python scripts/monitor_sessions.py realtime` |
| `fix_sessions.py full` | Исправить все | `python scripts/fix_sessions.py full` |
| `check_sessions.py` | Сессии в БД | `python scripts/check_sessions.py` |
| `check_ref_stats.py` | Статистика ссылок | `python scripts/check_ref_stats.py` |

### Настройка и установка

| Команда | Описание | Пример |
|---------|----------|---------|
| `setup_postgresql.py` | Установить PostgreSQL | `python scripts/setup_postgresql.py` |
| `setup_proxies.py` | Настроить прокси | `python scripts/setup_proxies.py` |
| `set_ref_links.py` | Массовые реф ссылки | `python scripts/set_ref_links.py` |
| `fix_database.py` | Исправить схему БД | `python scripts/fix_database.py` |

### Тестирование

| Команда | Описание | Пример |
|---------|----------|---------|
| `test_system.py` | Тест компонентов | `python scripts/test_system.py` |
| `test_openai.py` | Тест OpenAI | `python scripts/test_openai.py` |

---

## 🐳 Развертывание

### Docker развертывание

#### Быстрый запуск

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f lead_management

# Остановка
docker-compose down
```

#### Настройка для Docker

1. Скопируйте `.env.template` в `.env`
2. Заполните переменные окружения
3. Поместите `.session` файлы в `data/sessions/`
4. Настройте `data/proxies.json`

```yaml
# docker-compose.yml уже настроен для:
# - PostgreSQL база данных
# - Redis кэширование  
# - Nginx (опционально)
# - Автоматические бэкапы
```

### VPS развертывание

#### Подготовка сервера

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv postgresql nginx

# Клонирование проекта
git clone https://github.com/ваш-репозиторий/lead-system.git
cd lead-system

# Настройка окружения
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Systemd сервис

Создайте `/etc/systemd/system/lead-management.service`:

```ini
[Unit]
Description=Lead Management System
After=network.target postgresql.service

[Service]
Type=simple
User=lead
WorkingDirectory=/opt/lead-system
Environment=PATH=/opt/lead-system/venv/bin
ExecStart=/opt/lead-system/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Активация сервиса
sudo systemctl enable lead-management.service
sudo systemctl start lead-management.service

# Проверка статуса
sudo systemctl status lead-management.service
```

---

## ❓ Часто задаваемые вопросы

### Общие вопросы

**Q: Сколько сессий можно запустить одновременно?**
A: По умолчанию лимит 10 активных сессий. Можно изменить в настройках `SYSTEM__MAX_CONCURRENT_SESSIONS`.

**Q: Как часто система отвечает на сообщения?**
A: Задержка между ответами 5-45 секунд для имитации человека. Настраивается в `SECURITY__RESPONSE_DELAY_MIN/MAX`.

**Q: Можно ли использовать без прокси?**
A: Можно, но не рекомендуется. Создайте пустой `proxies.json` файл.

### Технические вопросы

**Q: Какие требования к серверу?**
A: Минимум: 2GB RAM, 2 CPU, 20GB SSD. Для 50+ сессий: 4GB RAM, 4 CPU.

**Q: Как добавить новую персону?**
A: Создайте класс в `personas/base/`, наследуя от `BasePersona`, и зарегистрируйте в `PersonaFactory`.

**Q: Что делать если OpenAI API дорогой?**
A: Смените модель на `gpt-4o-mini` в .env файле. Уменьшите `MAX_TOKENS`.

### Безопасность

**Q: Как защититься от блокировок Telegram?**
A: Используйте качественные прокси, не превышайте лимиты сообщений, добавляйте паузы между действиями.

**Q: Можно ли восстановить заблокированную сессию?**
A: Нет, нужно создавать новую сессию с другим номером телефона.

### Аналитика

**Q: Какая нормальная конверсия?**
A: 15-25% от первого сообщения до отправки реф ссылки считается хорошим результатом.

**Q: Как улучшить конверсию?**
A: Тестируйте разные персоны, улучшайте тексты, анализируйте на каких этапах теряются лиды.

### Поддержка

**Q: Где посмотреть логи ошибок?**
A: В файлах `logs/system.log` и `logs/errors.log`, или через `docker-compose logs`.

**Q: Что делать если система не запускается?**
A: Запустите `python scripts/quick_start.py` для диагностики всех компонентов.

---

## 🔗 Полезные ссылки

- 📖 [README.md](README.md) - Общая информация
- 🗺️ [ROADMAP.md](ROADMAP.md) - План развития  
- ✅ [SETUP_CHECKLIST.md](SETUP_CHECKLIST.md) - Чек-лист настройки
- 📋 [TODO.md](TODO.md) - Инструкции по разработке

---

## 🆘 Служба поддержки

При возникновении проблем:

1. **Проверьте диагностику**: `python scripts/quick_start.py`
2. **Попробуйте исправить**: `python scripts/fix_sessions.py full`  
3. **Проверьте логи**: `tail -f logs/system.log`
4. **Перезапустите**: `python main.py`

Система готова эффективно конвертить лидов! 🎯