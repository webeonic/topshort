# TopShort - Быстрый старт

## За 5 минут до первого запуска

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

### 2. Настройка проекта

```bash
# 1. Скопируйте .env.example
cp .env.example .env

# 2. Отредактируйте .env файл
nano .env  # или используйте любой редактор

# Минимальная конфигурация:
BINANCE_API_KEY=ваш_api_ключ_с_testnet
BINANCE_API_SECRET=ваш_secret_ключ
BINANCE_TESTNET=true

TELEGRAM_BOT_TOKEN=токен_от_botfather
TELEGRAM_CHAT_ID=ваш_chat_id

# 3. Установите зависимости и запустите
./run.sh
```

### 3. Первые команды

После запуска откройте вашего бота в Telegram:

```
/start     - Приветствие и список команд
/status    - Проверить статус бота
/scan      - Запустить первое сканирование (ручное)
/settings  - Посмотреть настройки
```

## Настройка для продакшена

### Важные параметры в .env

```bash
# Продакшен
BINANCE_TESTNET=false
BINANCE_API_KEY=ваш_продакшн_ключ
BINANCE_API_SECRET=ваш_продакшн_secret

# Консервативные настройки для старта
MARGIN_PER_TRADE=50.0          # Маленькая маржа
MAX_POSITIONS=5                # Мало позиций
MAX_TOTAL_MARGIN=250.0         # Ограниченный риск
DEFAULT_LEVERAGE=10            # Умеренное плечо
TAKE_PROFIT_PCT=5.0            # 5% профит

# Можно увеличивать постепенно:
# MARGIN_PER_TRADE=100.0
# MAX_POSITIONS=10
# DEFAULT_LEVERAGE=20
```

## Безопасность API ключей на Binance

1. Permissions: только "Enable Futures"
2. IP Whitelist: добавьте IP вашего сервера
3. Не давайте права на вывод средств

## Мониторинг

### Логи
```bash
# Смотреть логи в реальном времени
tail -f logs/topshort.log

# Последние 100 строк
tail -n 100 logs/topshort.log

# Поиск ошибок
grep ERROR logs/topshort.log
```

### Telegram уведомления

Бот будет автоматически присылать:
- ✅ Новые позиции
- 🔔 Закрытые позиции с P&L
- 🔍 Результаты сканирования
- ❌ Ошибки

## Частые вопросы

### Бот не открывает позиции?

Проверьте:
```
/status    - смотрите лимиты
/scan      - запустите ручное сканирование
/settings  - проверьте параметры
```

Возможные причины:
- Нет подходящих сигналов (рынок не подходит)
- Достигнуты лимиты MAX_POSITIONS или MAX_TOTAL_MARGIN
- Бот на паузе (используйте /resume)

### Как изменить настройки?

Через Telegram:
```
/set margin_per_trade 150
/set max_positions 15
/set default_leverage 25
```

Или отредактируйте .env и перезапустите бота.

### Как остановить бота?

```bash
# Через Telegram (рекомендуется)
/pause        # Приостановить торговлю
/closeall     # Закрыть все позиции
# Затем Ctrl+C в терминале

# Или просто
Ctrl+C в терминале
```

## Backup

Важные данные:
- `.env` - конфигурация (не коммитить!)
- `data/topshort.db` - база данных с историей

Регулярно делайте backup:
```bash
cp data/topshort.db data/backup_$(date +%Y%m%d).db
```

## Поддержка

- Документация: README.md
- Логи: logs/topshort.log
- Issues: создавайте в репозитории

---

**Удачной торговли! 🚀**
