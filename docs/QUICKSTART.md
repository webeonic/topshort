# TopShort - Быстрый старт

## 🚀 За 5 минут до первого запуска

### 1. Подготовка API ключей

#### Binance Testnet (для тестирования)
1. Перейдите на https://testnet.binancefuture.com/
2. Войдите через GitHub/Google
3. Получите тестовые USDT (кнопка "Get Test Funds")
4. Создайте API ключ: Account → API Management
5. Сохраните API Key и Secret Key

#### Telegram Bot
1. Найдите @BotFather в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Сохраните токен бота
5. Найдите @userinfobot и узнайте свой Chat ID

### 2. Установка и настройка

```bash
# 1. Клонируйте репозиторий
git clone <repository-url>
cd topshort

# 2. Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Настройте переменные окружения
cp .env.example .env
nano .env  # или используйте любой редактор
```

### 3. Минимальная конфигурация `.env`

```bash
# Binance API (Testnet для безопасного тестирования)
BINANCE_API_KEY=ваш_api_ключ_с_testnet
BINANCE_API_SECRET=ваш_secret_ключ
BINANCE_TESTNET=true

# Telegram Bot
TELEGRAM_BOT_TOKEN=токен_от_botfather
TELEGRAM_CHAT_ID=ваш_chat_id

# Торговые настройки (консервативные для старта)
MARGIN_PER_TRADE=50.0
MAX_POSITIONS=5
MAX_TOTAL_MARGIN=250.0
DEFAULT_LEVERAGE=10
TAKE_PROFIT_PCT=5.0
```

### 4. Запуск бота

```bash
python -m src.main
```

Или используйте удобный скрипт:
```bash
./run.sh
```

### 5. Первые команды в Telegram

После запуска откройте вашего бота в Telegram:

```
/start     - Приветствие и список команд
/menu      - Интерактивное меню с кнопками
/status    - Проверить статус бота
/scan      - Запустить первое сканирование вручную
/settings  - Посмотреть текущие настройки
```

## 📱 Интерактивные кнопки

Бот поддерживает удобное управление через кнопки:

### Главное меню (`/menu`)
- 📊 **Status** - Статус бота и позиции
- 💼 **Positions** - Все открытые позиции
- 📜 **History** - История сделок
- 📈 **Stats** - Статистика торговли
- ⚙️ **Settings** - Настройки
- ❓ **Help** - Справка

### Управление торговлей
- ▶️ **Resume** - Возобновить торговлю
- ⏸️ **Pause** - Приостановить торговлю
- 🔍 **Scan Now** - Запустить сканирование
- ❌ **Close All** - Закрыть все позиции

## 🔒 Безопасность API ключей на Binance

⚠️ **ВАЖНО:**

1. **Permissions**: только "Enable Futures"
2. **IP Whitelist**: добавьте IP вашего сервера
3. **Не давайте права на вывод средств**
4. **Никогда не коммитьте `.env` в git**
5. **Начните с testnet для тестирования**

## 📊 Автоматические миграции БД

Миграции базы данных применяются **АВТОМАТИЧЕСКИ** при каждом запуске!

- ✅ Создается бэкап перед миграцией
- ✅ Применяются только новые миграции
- ✅ Логируется весь процесс
- ✅ При ошибке - автоматический откат

Бэкапы сохраняются в: `data/topshort.db.backup_YYYYMMDD_HHMMSS`

## 🎯 Настройка для продакшена

### Важные параметры в `.env`

```bash
# Продакшен (после тестирования)
BINANCE_TESTNET=false
BINANCE_API_KEY=ваш_продакшн_ключ
BINANCE_API_SECRET=ваш_продакшн_secret

# Консервативные настройки для старта
MARGIN_PER_TRADE=50.0          # Маленькая маржа
MAX_POSITIONS=5                # Мало позиций
MAX_TOTAL_MARGIN=250.0         # Ограниченный риск
DEFAULT_LEVERAGE=10            # Умеренное плечо
TAKE_PROFIT_PCT=5.0            # 5% профит

# Можно увеличивать постепенно после успешных сделок
```

### Увеличение лимитов (когда наберетесь опыта)

```bash
MARGIN_PER_TRADE=100.0
MAX_POSITIONS=10
MAX_TOTAL_MARGIN=1000.0
DEFAULT_LEVERAGE=20
```

## 📈 Мониторинг

### Логи в реальном времени

```bash
# Смотреть логи
tail -f logs/topshort.log

# Последние 100 строк
tail -n 100 logs/topshort.log

# Поиск ошибок
grep ERROR logs/topshort.log

# Поиск открытых позиций
grep "Position opened" logs/topshort.log
```

### Telegram уведомления

Бот автоматически присылает:
- ✅ Новые открытые позиции с деталями
- 🔔 Закрытые позиции с P&L
- 🔍 Результаты сканирования рынка
- ❌ Ошибки и проблемы

## ❓ Частые вопросы

### Бот не открывает позиции?

Проверьте:
```
/status    - смотрите лимиты и статус
/scan      - запустите ручное сканирование
/settings  - проверьте параметры
```

Возможные причины:
- Нет подходящих сигналов (рынок не подходит под критерии)
- Достигнуты лимиты MAX_POSITIONS или MAX_TOTAL_MARGIN
- Бот на паузе (используйте `/resume`)
- Недостаточно средств на счете

### Как изменить настройки?

**Через Telegram** (рекомендуется):
```
/set margin_per_trade 150
/set max_positions 15
/set default_leverage 25
```

**Через .env** (требует перезапуска):
1. Отредактируйте `.env`
2. Перезапустите бота (Ctrl+C, затем запуск снова)

### Как остановить бота?

```bash
# Способ 1: Безопасная остановка через Telegram
/pause        # Приостановить торговлю
/closeall     # Закрыть все позиции (с подтверждением)
# Затем Ctrl+C в терминале

# Способ 2: Быстрая остановка
# Просто Ctrl+C в терминале
```

### Клавиатура не отображается?

```bash
# Проверить статус миграций
sqlite3 data/topshort.db "SELECT version FROM schema_migrations WHERE version='V002';"

# Если миграция не применена, перезапустите бота
# Миграции применяются автоматически при старте
```

### Где хранятся данные?

- `data/topshort.db` - основная база данных SQLite
- `logs/topshort.log` - логи работы бота
- `data/*.backup_*` - автоматические бэкапы БД

## 💾 Backup

Важные данные для бэкапа:
```bash
# Создать бэкап
cp .env .env.backup
cp data/topshort.db data/backup_$(date +%Y%m%d).db

# Регулярные бэкапы (добавьте в cron)
0 0 * * * cp ~/topshort/data/topshort.db ~/topshort/data/backup_$(date +\%Y\%m\%d).db
```

Не забудьте сохранить:
- `.env` - конфигурация (НЕ коммитить в git!)
- `data/topshort.db` - база данных с историей
- Binance API ключи (храните отдельно и безопасно)

## 🧪 Тестирование (опционально)

Если хотите запустить тесты:

```bash
# Установить зависимости для тестирования
pip install pytest pytest-cov pytest-mock

# Запустить все тесты
pytest

# Запустить с покрытием кода
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

Подробнее: [DEVELOPMENT.md](DEVELOPMENT.md)

## 📚 Дополнительная документация

- [README.md](../README.md) - Полная документация проекта
- [DEVELOPMENT.md](DEVELOPMENT.md) - Разработка и тестирование
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Развертывание на сервере
- [SSH-SETUP.md](../SSH-SETUP.md) - Настройка SSH доступа
- [docs/architecture/](architecture/) - Техническая архитектура

## 🎉 Готово!

Теперь ваш бот готов к работе:

1. ✅ Бот запущен и подключен к Telegram
2. ✅ База данных создана с автоматическими миграциями
3. ✅ Интерактивное меню работает
4. ✅ Автоматическое сканирование настроено
5. ✅ Уведомления приходят в Telegram

**Начните с testnet, протестируйте все функции, а затем переходите на продакшен!**

**Удачной торговли! 🚀**
