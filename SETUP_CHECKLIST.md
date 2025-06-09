# 🎯 Чек-лист настройки Lead Management System

## 📋 Обязательные шаги перед запуском

### 1. ⚙️ Настройка окружения

- [ ] Установлен Python 3.11+
- [ ] Создан виртуальное окружение: `python -m venv venv`
- [ ] Активировано окружение: `source venv/bin/activate` (Linux/Mac) или `venv\Scripts\activate` (Windows)
- [ ] Установлены зависимости: `pip install -r requirements.txt`

### 2. 📝 Конфигурация

- [ ] Скопирован файл настроек: `cp .env.template .env`
- [ ] Заполнены **все** обязательные переменные в `.env`:
  - [ ] `TELEGRAM__API_ID` - получить на https://my.telegram.org
  - [ ] `TELEGRAM__API_HASH` - получить на https://my.telegram.org  
  - [ ] `TELEGRAM__BOT_TOKEN` - получить у @BotFather
  - [ ] `TELEGRAM__ADMIN_IDS` - ваш Telegram ID (можно узнать у @userinfobot)
  - [ ] `OPENAI__API_KEY` - ключ API OpenAI
  - [ ] `DATABASE__PASSWORD` - пароль для PostgreSQL

### 3. 🗄️ База данных

- [ ] Установлен PostgreSQL 15+
- [ ] PostgreSQL запущен и доступен
- [ ] Создана база данных `lead_management`
- [ ] Пользователь `postgres` имеет доступ к базе

**Команды для PostgreSQL:**
```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres createdb lead_management

# macOS (Homebrew)
brew install postgresql
brew services start postgresql
createdb lead_management

# Docker
docker run -d --name postgres -e POSTGRES_DB=lead_management -e POSTGRES_PASSWORD=yourpass -p 5432:5432 postgres:15-alpine
```

### 4. 📱 Telegram сессии

- [ ] Создана папка для сессий: `mkdir -p data/sessions/`
- [ ] Добавлены `.session` файлы OR создать новые через скрипт:

```bash
# Создание новой сессии
python scripts/session_manager.py create session_name +1234567890 basic_man

# Проверка сессий
python scripts/session_manager.py list
```

### 5. 🌐 Прокси (опционально)

- [ ] Создан файл прокси: `cp data/proxies.json.example data/proxies.json`
- [ ] Настроены SOCKS5 прокси для каждой сессии
- [ ] Проверена доступность прокси

### 6. ✅ Проверка готовности

- [ ] Запущена проверка системы: `python scripts/quick_start.py`
- [ ] **Все 8 проверок пройдены успешно**

---

## 🚀 Первый запуск

### 1. Проверка компонентов

```bash
# Полная проверка системы
python scripts/quick_start.py
```

Должно показать: `✅ 8/8 проверок пройдено`

### 2. Запуск системы

```bash
python main.py
```

### 3. Проверка в Telegram боте

- [ ] Отправьте `/start` управляющему боту
- [ ] Проверьте что все сессии показываются как активные
- [ ] Убедитесь что аналитика работает
- [ ] Протестируйте отправку тестового сообщения

---

## 🎭 Настройка персон и проекта

### 1. Выбор персон для сессий

```bash
# Установка персоны для сессии
python scripts/session_manager.py persona session_name basic_man

# Доступные персоны:
# - basic_man (простой парень)
# - basic_woman (простая девушка)  
# - hyip_man (HYIP эксперт)
```

### 2. Настройка реферальных ссылок

```bash
# Установка реф ссылки для сессии
python scripts/session_manager.py reflink session_name "https://t.me/your_bot?start=ref123"
```

### 3. Настройка проекта

Отредактируйте функцию `setup_default_project()` в файле `personas/persona_factory.py`:

- [ ] Название проекта
- [ ] Описание 
- [ ] Преимущества
- [ ] Контакт поддержки
- [ ] Минимальная сумма инвестиций

---

## 📊 Мониторинг работы

### Логи системы

- `logs/system.log` - общие логи работы
- `logs/errors.log` - только ошибки

### Telegram бот управления

- **Дашборд** - общая статистика
- **Сессии** - управление аккаунтами
- **Диалоги** - просмотр бесед
- **Аналитика** - детальная статистика
- **Рассылки** - массовые уведомления

---

## ⚠️ Типичные проблемы

### База данных

**Проблема:** `connection refused`
**Решение:** Проверьте что PostgreSQL запущен: `sudo systemctl status postgresql`

### OpenAI API

**Проблема:** `Incorrect API key`  
**Решение:** Проверьте ключ на https://platform.openai.com/api-keys

### Telegram сессии

**Проблема:** `Session not authorized`
**Решение:** Пересоздайте сессию: `python scripts/session_manager.py create ...`

### Прокси

**Проблема:** `Connection timeout`
**Решение:** Проверьте доступность прокси и формат в `proxies.json`

---

## 🔒 Безопасность

### Обязательно:

- [ ] Используйте прокси для всех сессий
- [ ] Не превышайте лимиты сообщений (настроены в .env)
- [ ] Регулярно проверяйте статус сессий
- [ ] Делайте бэкапы базы данных

### Рекомендуется:

- [ ] Запуск на VPS с хорошей репутацией
- [ ] Использование разных IP для разных сессий
- [ ] Мониторинг блокировок в логах
- [ ] Резервные сессии для критических персон

---

## 📞 Поддержка

Если что-то не работает:

1. **Проверьте логи:** `tail -f logs/system.log`
2. **Запустите диагностику:** `python scripts/quick_start.py`
3. **Проверьте статус компонентов** в Telegram боте

**Система готова к работе когда:**
- ✅ Все проверки пройдены
- ✅ Есть авторизованные сессии  
- ✅ OpenAI API отвечает
- ✅ База данных подключена
- ✅ Управляющий бот работает

🎯 **Готово к конверсии лидов!**