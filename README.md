# TopShort - Automated Trading Bot for Binance Futures

Автоматический торговый бот для открытия шорт-позиций на Binance Futures по парам, которые остывают после пампа.

## Описание

TopShort - это полностью автоматизированный торговый бот, который:

- **Сканирует рынок** каждый час для поиска торговых возможностей
- **Находит пары**, которые показали сильный рост (≥30% за 48-72 часа), но начали остывать (снижение объемов за последние 4-8 часов)
- **Открывает short позиции** с настраиваемым leverage и маржой
- **Автоматически закрывает** позиции по достижению Take-Profit (5%)
- **Контролирует риски**: ограничения по количеству позиций и суммарной марже
- **Управляется через Telegram**: полный контроль через бот

## Архитектура

```
┌─────────────────────┐
│   Telegram Bot      │  ← Интерфейс управления
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Trading Engine     │  ← Координация всех компонентов
└──────────┬──────────┘
           │
    ┌──────┴──────┬──────────┬──────────┐
    ▼             ▼          ▼          ▼
┌───────┐   ┌──────────┐ ┌──────┐  ┌────────┐
│Scanner│   │Position  │ │Risk  │  │Binance │
│       │   │Manager   │ │Mgr   │  │Client  │
└───────┘   └──────────┘ └──────┘  └────────┘
    │                                    │
    └────────────────┬───────────────────┘
                     ▼
              ┌────────────┐
              │  Database  │
              │  (SQLite)  │
              └────────────┘
```

## Технологии

- **Python 3.11+**
- **CCXT** - для работы с Binance REST API
- **python-telegram-bot** - для Telegram интеграции
- **SQLAlchemy** - ORM для SQLite
- **APScheduler** - планировщик задач

## Установка

### 1. Клонируйте репозиторий

```bash
git clone <repository-url>
cd topshort
```

### 2. Создайте виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env` файл:

```bash
# Binance API (получить на https://www.binance.com/en/my/settings/api-management)
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here
BINANCE_TESTNET=true  # true для testnet, false для live

# Telegram Bot (создать через @BotFather)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here  # Ваш Telegram ID

# Торговые настройки (по умолчанию)
MARGIN_PER_TRADE=100.0        # Маржа на одну сделку (USDT)
MAX_POSITIONS=10              # Макс. одновременных позиций
MAX_TOTAL_MARGIN=1000.0       # Макс. суммарная маржа (USDT)
DEFAULT_LEVERAGE=20           # Плечо по умолчанию
TAKE_PROFIT_PCT=5.0           # Take-profit в %

# Параметры сканирования
PUMP_THRESHOLD_PCT=30.0       # Мин. рост для определения пампа
PUMP_PERIOD_HOURS_MIN=48      # Мин. период для пампа
PUMP_PERIOD_HOURS_MAX=72      # Макс. период для пампа
COOLDOWN_PERIOD_HOURS_MIN=4   # Мин. период остывания
COOLDOWN_PERIOD_HOURS_MAX=8   # Макс. период остывания
VOLUME_DECREASE_THRESHOLD_PCT=20.0  # Порог снижения объема

# Расписание
SCAN_INTERVAL_MINUTES=60      # Интервал сканирования рынка
MONITOR_INTERVAL_SECONDS=30   # Интервал мониторинга позиций

# Режимы стратегий
DEFAULT_MANUAL_STRATEGY_MODE=pump_cooldown  # Что запускает /scan без аргументов
OB_CYCLE_INTERVAL_SECONDS=60   # Пауза между циклами OrderBlock
OB_TOP_PAIRS_LIMIT=50          # Кол-во пар в непрерывном OrderBlock-скане
```

### 5. Получение Telegram Chat ID

Чтобы узнать свой Telegram Chat ID:

1. Напишите боту @userinfobot
2. Он пришлет ваш ID
3. Используйте этот ID в `.env` файле

## Запуск

### Запуск бота

```bash
python -m src.main
```

Или:

```bash
python src/main.py
```

### Тестирование на Testnet

Для безопасного тестирования используйте Binance Testnet:

1. Зарегистрируйтесь на https://testnet.binancefuture.com/
2. Получите API ключи
3. Установите `BINANCE_TESTNET=true` в `.env`

## Команды Telegram

| Команда | Описание |
|---------|----------|
| `/start` | Запуск бота и описание |
| `/status` | Текущий статус и открытые позиции |
| `/positions` | Список всех открытых позиций |
| `/history` | История последних 10 сделок |
| `/stats` | Статистика торговли |
| `/settings` | Текущие настройки |
| `/set <key> <value>` | Изменить настройку |
| `/pause` | Приостановить торговлю |
| `/resume` | Возобновить торговлю |
| `/scan [mode]` | Запустить сканирование вручную (`/scan ob` для SMC) |
| `/pairs` | Показать текущий список топ-пар и источник данных |
| `/close <symbol>` | Закрыть позицию по символу |
| `/closeall` | Закрыть все позиции |
| `/help` | Справка по командам |

### Примеры

```bash
# Изменить маржу на сделку
/set margin_per_trade 150

# Изменить максимальное количество позиций
/set max_positions 15

# Изменить leverage
/set default_leverage 25

# Закрыть конкретную позицию
/close BTC/USDT:USDT
```

## Логика торговли

### Pump & Cooldown (классическая стратегия)

1. **Пампы**: рост ≥30% за 48–72 часа.
2. **Кулдаун**: падение объёма ≥20% за 4–8 часов.
3. **Инструменты**: USDT perpetual futures.

После детекции Risk Manager проверяет лимиты и открывает **short** позицию с фиксированным TP (по умолчанию 5%). Команда `/scan` без аргументов запускает именно эту стратегию.

### Order Block Breakout + FVG (SMC)

- Мульти-таймфрейм анализ (по умолчанию 1D/4H/1H/15m/5m).
- Определение структуры рынка (BOS/CHoCH), свежих Order Blocks и Fair Value Gaps.
- Объёмные фильтры (`volume_ma_period`, `volume_spike_threshold`) и временные окна ICT Silver Bullet.
- Может открывать **long** и **short** позиции; TP/SL берутся из сигнала.

Основные переменные окружения:

| Переменная | Значение по умолчанию | Описание |
|------------|----------------------|----------|
| `OB_STRATEGY_ENABLED` | `true` | Включить стратегию |
| `OB_TIMEFRAMES` | `1d,4h,1h,15m,5m` | Таймфреймы анализа |
| `OB_SESSION_WINDOWS` | `London:08:00-09:00,...` | Сессии (UTC) |
| `OB_MIN_FVG_SIZE_PCT` | `0.3` | Минимальный размер FVG (%) |
| `OB_VOLUME_SPIKE_THRESHOLD` | `1.2` | Множитель объёма для подтверждения |
| `TOP_PAIRS_COUNT` | `50` | Количество пар из CoinGecko |

Команда `/pairs` показывает актуальный список топ-пар (данные кэшируются и обновляются планировщиком). Чтобы запустить стратегию, используйте `/scan ob`.

### Управление позициями

- Take-profit лимит ставится сразу после открытия (для long/short с учётом направления).
- Бот отслеживает достижение TP и опционального SL (`stop_loss_price` из сигнала).
- Позиции можно закрывать вручную `/close` или `/closeall`.

## Управление рисками

Бот имеет встроенные механизмы контроля рисков:

- **Максимальное количество позиций**: предотвращает избыточную диверсификацию
- **Максимальная суммарная маржа**: ограничивает общий риск
- **Фиксированная маржа на сделку**: контролируемый размер каждой позиции
- **Take-Profit**: автоматическая фиксация прибыли

## Структура проекта

```
topshort/
├── src/
│   ├── main.py                 # Точка входа
│   ├── config.py               # Конфигурация
│   ├── database/
│   │   ├── models.py          # Модели БД
│   │   └── repository.py      # CRUD операции
│   ├── exchange/
│   │   ├── binance_client.py  # CCXT wrapper
│   │   └── market_data.py     # Анализ рыночных данных
│   ├── strategy/
│   │   ├── detector.py        # Детекция пампа
│   │   └── scanner.py         # Сканирование рынка
│   ├── trading/
│   │   ├── engine.py          # Торговый движок
│   │   ├── position_manager.py # Управление позициями
│   │   └── risk_manager.py    # Управление рисками
│   ├── bot/
│   │   ├── telegram_bot.py    # Telegram bot
│   │   └── commands.py        # Команды бота
│   └── scheduler/
│       └── jobs.py            # Планировщик задач
├── data/                      # База данных SQLite
├── logs/                      # Логи
├── tests/                     # Тесты
├── requirements.txt           # Зависимости
├── .env.example              # Пример конфигурации
└── README.md                 # Документация
```

## База данных

Бот использует SQLite для хранения:

- **Settings**: Настройки торговли
- **Position**: Открытые позиции
- **TradeHistory**: История сделок
- **MarketSignal**: Сигналы рынка
- **BotStatus**: Статус бота

База создается автоматически при первом запуске в `./data/topshort.db`.

## Логирование

Логи сохраняются в `./logs/topshort.log` и выводятся в консоль с цветовым кодированием.

Уровень логирования настраивается через `LOG_LEVEL` в `.env`.

## Бэктестинг

Для оффлайн-проверки стратегии Order Block Breakout доступен CLI:

```bash
python scripts/run_backtest.py --top 10 --max-trades 100
# или указать конкретные инструменты
python scripts/run_backtest.py --symbols BTC/USDT:USDT,ETH/USDT:USDT
```

Скрипт использует реальные данные Binance (testnet/live в зависимости от `.env`), генерирует отчёт (win rate, expectancy, profit factor) и сохраняет сделки в `backtest_trades.json` для дальнейшего анализа.

## Безопасность

⚠️ **ВАЖНО:**

- Никогда не коммитьте файл `.env` в git
- Храните API ключи в безопасности
- Начните с testnet для тестирования
- Используйте ограниченные API ключи (только futures trading)
- Установите IP whitelist на Binance для API ключей

## Мониторинг

Бот отправляет уведомления в Telegram:

- ✅ Новые открытые позиции
- 🔔 Закрытые позиции с P&L
- 🔍 Результаты сканирования
- ❌ Ошибки и проблемы

## Тестирование

```bash
# Запустить тесты
pytest

# С покрытием
pytest --cov=src
```

## Troubleshooting

### Ошибка "BINANCE_API_KEY is required"

Проверьте, что файл `.env` существует и содержит все необходимые переменные.

### Ошибка "Insufficient data"

Некоторые пары могут не иметь достаточной истории. Это нормально, бот пропустит их.

### Позиции не открываются

Проверьте:
- Достигнуты ли лимиты (max_positions, max_total_margin)
- Есть ли подходящие сигналы (`/scan`)
- Не приостановлен ли бот (`/resume`)

## Лицензия

MIT

## Disclaimer

Этот бот предоставляется "как есть". Торговля на финансовых рынках несет риски. Используйте на свой страх и риск. Автор не несет ответственности за финансовые потери.

## 📚 Документация

Документация проекта теперь организована в отдельной директории:

### Быстрый старт
- **[docs/QUICKSTART.md](docs/QUICKSTART.md)** - Установка и запуск за 5 минут
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Развертывание на сервере
- **[SSH-SETUP.md](SSH-SETUP.md)** - Настройка SSH доступа

### Для разработчиков
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Руководство разработчика
  - Настройка окружения
  - Тестирование (160+ тестов)
  - Миграции базы данных
  - Отладка
- **[docs/CI_CD_QUICKSTART.md](docs/CI_CD_QUICKSTART.md)** - CI/CD за 5 минут
- **[docs/CI_CD.md](docs/CI_CD.md)** - Полная документация CI/CD

### Техническая архитектура
- **[docs/architecture/](docs/architecture/)** - Детальная техническая документация
  - [KEYBOARD_SYSTEM.md](docs/architecture/KEYBOARD_SYSTEM.md) - Система интерактивных клавиатур
  - [POSITION_TRACKING.md](docs/architecture/POSITION_TRACKING.md) - Управление позициями
  - [TESTING.md](docs/architecture/TESTING.md) - Документация по тестам

## Поддержка

Для вопросов и проблем создавайте Issue в репозитории.
