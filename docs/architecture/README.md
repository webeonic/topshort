# TopShort - Техническая архитектура

Эта директория содержит детальную техническую документацию для разработчиков.

## 📚 Документы

### [KEYBOARD_SYSTEM.md](KEYBOARD_SYSTEM.md)
**Система динамических клавиатур Telegram**

Полное описание системы интерактивных клавиатур:
- Архитектура (Models, Repositories, Builders, Handlers)
- База данных (4 таблицы: templates, buttons, states, logs)
- Создание кастомных клавиатур
- Обработка callback'ов
- Аналитика взаимодействий

**Для кого**: разработчики, работающие с Telegram UI

---

### [POSITION_TRACKING.md](POSITION_TRACKING.md)
**Мульти-источниковое отслеживание позиций и лимит-ордера**

Детальное руководство по системе управления позициями:
- Отслеживание позиций из разных источников (bot, manual, external)
- Автоматическое размещение take-profit лимит-ордеров
- Синхронизация с биржей (импорт внешних позиций)
- Мониторинг и управление ордерами
- Контроль лимитов по всем источникам

**Для кого**: разработчики торговой логики, интеграции с биржей

---

### [TESTING.md](TESTING.md)
**Полная документация по тестированию**

Comprehensive test suite documentation:
- Структура тестов (160+ тестов, 6 файлов)
- Фикстуры и моки
- Покрытие кода (~90% для core модулей)
- Best practices
- CI/CD интеграция

**Для кого**: разработчики, QA, DevOps

---

## 🗺️ Обзор архитектуры

```
┌─────────────────────┐
│   Telegram Bot      │  ← Интерфейс управления (Keyboard System)
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Trading Engine     │  ← Координация компонентов
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
              │  Database  │  ← SQLite + Auto Migrations
              │  (SQLite)  │
              └────────────┘
```

## 🔑 Ключевые компоненты

### Trading Layer
- **Position Manager** - управление позициями
- **Risk Manager** - контроль рисков
- **Exchange Position Sync** - синхронизация с биржей
- **Limit Order Monitor** - мониторинг ордеров
- **Scanner** - поиск торговых сигналов

### Database Layer
- **Models** - SQLAlchemy модели
- **Repositories** - паттерн Repository
- **Migration Manager** - автоматические миграции
- Таблицы: positions, trade_history, limit_orders, settings, etc.

### Bot Layer
- **Telegram Bot** - интеграция с Telegram API
- **Commands** - обработка команд
- **Keyboard Builder** - построение клавиатур
- **Callback Handler** - обработка взаимодействий

### Strategy Layer
- **Detector** - детекция пампов и остывания
- **Scanner** - сканирование рынка
- **Order Block Breakout Strategy** - мульти-таймфрейм SMC анализ, объединённый с FVG/volume фильтрами

### Data Services
- **Top Pairs Service** - ежедневный сбор топ-50 монет по капитализации через CoinGecko, маппинг на USDT-пары Binance и кэширование в `data/top_pairs_cache.json`. Сервис используется торговым движком, ботом и планировщиком, автоматически обновляется и предоставляет fallback-список при сбоях API.

## 🛠️ Паттерны проектирования

- **Repository Pattern** - абстракция доступа к данным
- **Builder Pattern** - построение клавиатур
- **Strategy Pattern** - роутинг callback'ов
- **Decorator Pattern** - логирование и обработка ошибок
- **Template Method** - инициализация клавиатур

## 📊 База данных

### Основные таблицы

**Торговые данные:**
- `positions` - открытые позиции
- `trade_history` - история сделок
- `limit_orders` - лимит-ордера
- `market_signals` - сигналы сканирования

**Конфигурация:**
- `settings` - настройки бота
- `bot_status` - статус работы

**Telegram UI:**
- `keyboard_templates` - шаблоны клавиатур
- `keyboard_buttons` - кнопки
- `keyboard_states` - состояния пользователей
- `callback_logs` - логи взаимодействий

**Служебные:**
- `schema_migrations` - история миграций

## 🔄 Жизненный цикл позиции

```
1. Scanner находит сигнал
         ↓
2. Risk Manager проверяет лимиты
         ↓
3. Position Manager открывает позицию
         ↓
4. Автоматически размещается TP лимит-ордер
         ↓
5. Limit Order Monitor отслеживает ордер
         ↓
6. При заполнении ордера позиция закрывается
         ↓
7. Результат записывается в trade_history
```

## 🔐 Безопасность

- **API ключи** хранятся в `.env` (не коммитятся)
- **Validation** на уровне моделей и репозиториев
- **SQL injection protection** через SQLAlchemy ORM
- **Audit logging** для чувствительных операций
- **Rate limiting** для взаимодействия с биржей

## 📈 Масштабируемость

- **Database-driven configuration** - изменения без перезапуска
- **Stateless handlers** - горизонтальное масштабирование
- **Batch operations** - эффективные запросы к бирже
- **Analytics-ready** - сбор метрик для оптимизации

## 🧪 Тестирование

- **Unit tests** - изолированные тесты компонентов
- **In-memory database** - быстрые тесты БД
- **Mocked exchange** - без реальных API вызовов
- **90%+ coverage** - высокое покрытие критической логики

См. [TESTING.md](TESTING.md) для деталей.

## 🚀 Для новых разработчиков

1. Начните с [../DEVELOPMENT.md](../DEVELOPMENT.md)
2. Изучите [TESTING.md](TESTING.md) для понимания тестов
3. Прочитайте [KEYBOARD_SYSTEM.md](KEYBOARD_SYSTEM.md) для работы с UI
4. Изучите [POSITION_TRACKING.md](POSITION_TRACKING.md) для торговой логики

## 📞 Дополнительные ресурсы

- [Основной README](../../README.md)
- [Quick Start](../QUICKSTART.md)
- [Development Guide](../DEVELOPMENT.md)
- [Deployment](../../DEPLOYMENT.md)

---

**Вопросы?** Создайте Issue в репозитории.
