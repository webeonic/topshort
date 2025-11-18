# TopShort - Руководство разработчика

Это руководство для разработчиков, работающих над проектом TopShort.

## 📋 Содержание

- [Настройка окружения](#настройка-окружения)
- [Тестирование](#тестирование)
- [Миграции базы данных](#миграции-базы-данных)
- [Архитектура](#архитектура)
- [Разработка новых функций](#разработка-новых-функций)
- [Отладка](#отладка)
- [CI/CD](#cicd)

## 🛠️ Настройка окружения

### 1. Клонирование и установка

```bash
# Клонировать репозиторий
git clone <repository-url>
cd topshort

# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установить основные зависимости
pip install -r requirements.txt

# Установить зависимости для разработки
pip install -r requirements-test.txt
```

### 2. Зависимости для разработки

```bash
# Тестирование
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.1
pytest-asyncio>=0.21.0

# Линтеры и форматирование
black>=23.7.0
flake8>=6.0.0
mypy>=1.4.1
isort>=5.12.0

# Дополнительные инструменты
ipython>=8.14.0
ipdb>=0.13.13
```

### 3. Pre-commit hooks (рекомендуется)

```bash
# Установить pre-commit
pip install pre-commit

# Настроить hooks
pre-commit install

# Запустить на всех файлах
pre-commit run --all-files
```

## 🧪 Тестирование

### Структура тестов

```
tests/
├── conftest.py                          # Общие фикстуры
├── test_database_models.py              # Тесты моделей БД
├── test_database_repository.py          # Тесты репозиториев
├── test_position_manager.py             # Тесты управления позициями
├── test_risk_manager.py                 # Тесты управления рисками
├── test_exchange_position_sync.py       # Тесты синхронизации с биржей
└── test_limit_order_monitor.py          # Тесты мониторинга ордеров
```

### Базовые команды тестирования

```bash
# Запустить все тесты
pytest

# С подробным выводом
pytest -v

# Конкретный файл
pytest tests/test_position_manager.py

# Конкретный тест
pytest tests/test_position_manager.py::TestOpenPosition::test_open_position_success

# С покрытием кода
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Только быстрые тесты
pytest -m "not slow"

# В параллель (быстрее)
pytest -n auto

# Остановиться на первой ошибке
pytest -x

# Показать локальные переменные при ошибках
pytest --showlocals

# Запустить последние упавшие тесты
pytest --lf
```

### Отладка тестов

```bash
# Войти в отладчик при ошибке
pytest --pdb

# Показать полный traceback
pytest --tb=long

# Без захвата вывода (print будет виден)
pytest -s

# Детальный вывод
pytest -vv --capture=no
```

### Написание тестов

#### Использование фикстур

```python
import pytest

def test_position_creation(test_db_session, mock_binance_client):
    """Тест создания позиции."""
    from src.database.repository import PositionRepository

    repo = PositionRepository(test_db_session)
    position = repo.create(
        symbol="BTC/USDT:USDT",
        entry_price=50000.0,
        quantity=0.1,
        margin=100.0,
        leverage=20,
        side="short",
        source="bot_auto"
    )

    assert position.id is not None
    assert position.symbol == "BTC/USDT:USDT"
    assert position.status == "open"
```

#### Мокирование внешних зависимостей

```python
from unittest.mock import Mock, patch

def test_open_position_with_mock(test_db_session):
    """Тест с мокированием биржи."""
    mock_client = Mock()
    mock_client.create_order.return_value = {
        'id': 'order123',
        'status': 'open',
        'price': 50000.0
    }

    manager = PositionManager(test_db_session, mock_client, config)
    result = manager.open_position("BTC/USDT:USDT", 100.0, 20)

    assert result['success'] is True
    mock_client.create_order.assert_called_once()
```

#### Параметризованные тесты

```python
@pytest.mark.parametrize("entry,exit,expected_pnl", [
    (50000, 47500, 250.0),
    (100000, 95000, 500.0),
    (1000, 950, 5.0),
])
def test_pnl_calculation(entry, exit, expected_pnl):
    """Тест расчета P&L."""
    quantity = 0.1
    pnl = (entry - exit) * quantity
    assert pnl == expected_pnl
```

### Покрытие кода

Текущее покрытие:

| Модуль | Покрытие | Тестов |
|--------|----------|--------|
| database/models.py | ~95% | 30+ |
| database/repository.py | ~90% | 50+ |
| trading/position_manager.py | ~85% | 25+ |
| trading/risk_manager.py | ~90% | 30+ |
| trading/exchange_position_sync.py | ~80% | 15+ |
| trading/limit_order_monitor.py | ~80% | 12+ |

**Всего**: 160+ тестов, ~3000 строк тестового кода

## 🗄️ Миграции базы данных

### Автоматические миграции

Миграции применяются **автоматически** при каждом запуске бота!

```python
from src.database.models import create_database

# Миграции применятся автоматически
engine = create_database('sqlite:///data/topshort.db')
```

### Создание новой миграции

```bash
# 1. Создать SQL файл с версией
nano src/database/migrations/scripts/V003__your_feature.sql
```

```sql
-- V003: Add notes column to positions
-- Author: Your Name
-- Date: 2025-01-18

ALTER TABLE positions ADD COLUMN notes TEXT;

-- Create index for performance
CREATE INDEX idx_positions_notes ON positions(notes) WHERE notes IS NOT NULL;
```

```bash
# 2. Коммит
git add src/database/migrations/scripts/V003__your_feature.sql
git commit -m "feat: add notes column to positions"

# 3. При следующем запуске бота миграция применится автоматически!
```

### Соглашения об именовании миграций

**Формат**: `V{XXX}__{описание}.sql`

- `XXX` - номер версии (001, 002, 003, ...)
- `описание` - краткое описание через snake_case

**Примеры**:
- `V001__add_multi_source_tracking.sql`
- `V002__add_dynamic_keyboard_system.sql`
- `V003__add_position_notes.sql`
- `V004__optimize_query_indexes.sql`

### Проверка статуса миграций

```bash
# Проверить применённые миграции
python scripts/check_migrations.py data/topshort.db

# Или через SQL
sqlite3 data/topshort.db "SELECT * FROM schema_migrations ORDER BY version;"
```

### Откат миграции

```bash
# 1. Найти последний бэкап
ls -lh data/*.backup*

# 2. Восстановить из бэкапа
cp data/topshort.db.backup_20250118_120000 data/topshort.db

# 3. Перезапустить бота
python -m src.main
```

### Бэкапы

Автоматические бэкапы создаются перед каждой миграцией:
```
data/topshort.db.backup_YYYYMMDD_HHMMSS
```

Ручной бэкап:
```bash
cp data/topshort.db data/manual_backup_$(date +%Y%m%d_%H%M%S).db
```

## 🏗️ Архитектура

### Структура проекта

```
topshort/
├── src/
│   ├── main.py                         # Точка входа
│   ├── config.py                       # Конфигурация
│   ├── database/
│   │   ├── models.py                   # Модели SQLAlchemy
│   │   ├── repository.py               # Репозитории (CRUD)
│   │   ├── migrations/                 # Система миграций
│   │   │   ├── migration_manager.py
│   │   │   └── scripts/                # SQL миграции
│   │   └── migrate_v1.py               # Legacy (deprecated)
│   ├── exchange/
│   │   ├── binance_client.py           # CCXT wrapper
│   │   └── market_data.py              # Анализ рынка
│   ├── strategy/
│   │   ├── detector.py                 # Детекция пампа
│   │   └── scanner.py                  # Сканирование
│   ├── trading/
│   │   ├── engine.py                   # Торговый движок
│   │   ├── position_manager.py         # Управление позициями
│   │   ├── risk_manager.py             # Управление рисками
│   │   ├── exchange_position_sync.py   # Синхронизация с биржей
│   │   └── limit_order_monitor.py      # Мониторинг ордеров
│   ├── bot/
│   │   ├── telegram_bot.py             # Telegram бот
│   │   ├── commands.py                 # Команды
│   │   ├── callback_handler.py         # Обработка кнопок
│   │   ├── keyboard_builder.py         # Построение клавиатур
│   │   └── keyboard_init.py            # Инициализация клавиатур
│   └── scheduler/
│       └── jobs.py                     # Планировщик задач
├── tests/                              # Тесты
├── data/                               # База данных SQLite
├── logs/                               # Логи
├── docs/                               # Документация
│   ├── QUICKSTART.md
│   ├── DEVELOPMENT.md
│   └── architecture/                   # Детальная техническая документация
└── scripts/                            # Утилиты
```

### Основные компоненты

**Trading Engine** - координирует все компоненты:
- Scanner - находит сигналы на рынке
- Risk Manager - проверяет лимиты
- Position Manager - открывает/закрывает позиции
- Limit Order Monitor - отслеживает TP ордера

**Telegram Bot** - интерфейс управления:
- Команды (/start, /status, /positions, etc.)
- Интерактивные клавиатуры (inline keyboards)
- Callback handlers - обработка нажатий кнопок

**Database Layer** - персистентность:
- Models - SQLAlchemy модели
- Repositories - паттерн Repository для CRUD
- Migrations - автоматическая миграция схемы

Подробнее: [docs/architecture/](architecture/)

## 🔧 Разработка новых функций

### 1. Добавление новой команды Telegram

**Шаг 1**: Добавить обработчик в `src/bot/commands.py`:

```python
async def my_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Описание команды."""
    # Получить данные
    data = self.some_repo.get_data()

    # Построить сообщение
    message = f"Результат: {data}"

    # Добавить клавиатуру (опционально)
    keyboard = self.keyboard_builder.build_inline_keyboard_from_template('my_menu')

    await update.message.reply_text(message, reply_markup=keyboard)
```

**Шаг 2**: Зарегистрировать в `src/bot/telegram_bot.py`:

```python
self.application.add_handler(CommandHandler("mycommand", self.commands.my_command))
```

### 2. Добавление новой кнопки в клавиатуру

**Через базу данных** (рекомендуется):

```python
# В src/bot/keyboard_init.py
button_repo.create(
    template_id=template.id,
    label="🎯 Моя кнопка",
    callback_data="my_action",
    row_position=0,
    column_position=0,
    button_type="callback",
    action="my_action"
)
```

**Программно**:

```python
buttons_data = [
    {'text': '🎯 Моя кнопка', 'callback_data': 'my_action'}
]
keyboard = builder.create_inline_keyboard(buttons_data)
```

### 3. Добавление обработчика callback

В `src/bot/callback_handler.py`:

```python
# Регистрация
self.register('my_action', self.handle_my_action)

# Обработчик
@log_callback(success=True)
async def handle_my_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Обработано!")

    # Обновить сообщение
    await query.edit_message_text("Новый текст ✅")
```

### 4. Добавление новой таблицы в БД

**Шаг 1**: Добавить модель в `src/database/models.py`:

```python
class MyNewTable(Base):
    __tablename__ = 'my_new_table'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    value = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_my_new_table_name', 'name'),
    )
```

**Шаг 2**: Создать миграцию:

```sql
-- V00X__add_my_new_table.sql
CREATE TABLE my_new_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    value FLOAT DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_my_new_table_name ON my_new_table(name);
```

**Шаг 3**: Добавить репозиторий в `src/database/repository.py`:

```python
class MyNewTableRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, name: str, value: float) -> MyNewTable:
        obj = MyNewTable(name=name, value=value)
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def get(self, id: int) -> Optional[MyNewTable]:
        return self.session.query(MyNewTable).filter_by(id=id).first()
```

## 🐛 Отладка

### Логирование

```python
import logging

logger = logging.getLogger(__name__)

# Уровни логирования
logger.debug("Детальная информация")
logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
logger.exception("Ошибка с traceback")
```

### Настройка уровня логов

В `.env`:
```bash
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### Отладка в IDE

**VSCode** - создать `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Main",
            "type": "python",
            "request": "launch",
            "module": "src.main",
            "console": "integratedTerminal",
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        }
    ]
}
```

**PyCharm**: Run → Edit Configurations → Add Python → Module name: `src.main`

### Отладка тестов

```bash
# Войти в ipdb при ошибке
pytest --pdb

# Использовать ipdb в коде
import ipdb; ipdb.set_trace()
```

### Проверка БД

```bash
# Открыть БД в интерактивном режиме
sqlite3 data/topshort.db

# Полезные команды
.tables                          # Показать все таблицы
.schema positions                # Показать схему таблицы
SELECT * FROM positions LIMIT 5; # Посмотреть данные
.exit                            # Выйти
```

## 🚀 CI/CD

**Подробная документация:** [docs/CI_CD.md](CI_CD.md)
**Быстрый старт:** [docs/CI_CD_QUICKSTART.md](CI_CD_QUICKSTART.md)

### GitHub Actions (пример)

`.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-test.txt

    - name: Run tests
      run: pytest --cov=src --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

### Pre-commit hooks

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black

  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
```

## 📚 Дополнительные ресурсы

### Внешняя документация

- [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/14/orm/)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)
- [CCXT](https://docs.ccxt.com/)
- [pytest](https://docs.pytest.org/)
- [Binance Futures API](https://binance-docs.github.io/apidocs/futures/en/)

### Внутренняя документация

- [docs/architecture/KEYBOARD_SYSTEM.md](architecture/KEYBOARD_SYSTEM.md) - Система клавиатур
- [docs/architecture/POSITION_TRACKING.md](architecture/POSITION_TRACKING.md) - Отслеживание позиций
- [docs/architecture/TESTING.md](architecture/TESTING.md) - Детали тестирования

## ✅ Checklist для Pull Request

Перед созданием PR убедитесь:

- [ ] Все тесты проходят (`pytest`)
- [ ] Покрытие кода не уменьшилось
- [ ] Код отформатирован (`black src/ tests/`)
- [ ] Нет ошибок линтера (`flake8 src/`)
- [ ] Обновлена документация (если нужно)
- [ ] Добавлены миграции БД (если нужно)
- [ ] Коммит-сообщения информативные
- [ ] `.env` не закоммичен

## 🎯 Best Practices

1. **Всегда пишите тесты** для нового кода
2. **Используйте type hints** для лучшей читаемости
3. **Логируйте важные события** (открытие позиций, ошибки)
4. **Обрабатывайте ошибки** gracefully
5. **Документируйте сложную логику**
6. **Делайте атомарные коммиты**
7. **Code review обязателен**
8. **Тестируйте на testnet** перед продакшеном

---

**Happy coding!** 🎉
