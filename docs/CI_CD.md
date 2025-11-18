# CI/CD - Полная документация

## 📋 Обзор

Этот проект настроен с комплексным CI/CD pipeline, который автоматически запускает тесты, проверки качества кода и сканирование безопасности при каждом push и pull request.

## 🎯 Что настроено

### GitHub Actions Workflows

#### 1. Tests Workflow (`.github/workflows/tests.yml`)

**Триггеры:** Push и PR в ветки main/master/develop

**Функциональность:**
- ✅ Запуск тестов на Python 3.10, 3.11, 3.12 (matrix testing)
- ✅ Генерация отчетов о покрытии кода
- ✅ Загрузка coverage на Codecov
- ✅ Проверка минимального порога покрытия (80%)
- ✅ Кеширование зависимостей для ускорения
- ✅ Запуск линтинга и проверки типов
- ✅ Параллельное выполнение для скорости

**Matrix Testing:**
```yaml
Python версии: 3.10, 3.11, 3.12
OS: Ubuntu Latest
Параллельно: 3 job'а одновременно
```

#### 2. Code Quality Workflow (`.github/workflows/code-quality.yml`)

**Триггеры:** Push и PR в ветки main/master/develop

**Проверки:**
- ✅ **Black** - проверка форматирования кода (line-length=127)
- ✅ **isort** - проверка сортировки импортов
- ✅ **Flake8** - линтинг (max-complexity=10)
- ✅ **MyPy** - проверка типов (strict на src/)
- ✅ **Bandit** - сканирование безопасности (Low/Medium severity)
- ✅ **Safety** - проверка уязвимостей в зависимостях
- ✅ **Radon** - анализ сложности кода

### Pre-commit Hooks

#### `.pre-commit-config.yaml`

Автоматические проверки перед каждым коммитом:

**Базовые проверки:**
- ✅ Удаление trailing whitespace
- ✅ Фикс end-of-file
- ✅ Проверка YAML/JSON синтаксиса
- ✅ Детектирование приватных ключей
- ✅ Проверка больших файлов

**Код качество:**
- ✅ Форматирование кода (Black)
- ✅ Сортировка импортов (isort)
- ✅ Линтинг (Flake8)
- ✅ Проверка типов (MyPy)
- ✅ Безопасность (Bandit)
- ✅ Запуск тестов с проверкой покрытия

### Конфигурационные файлы

#### `pyproject.toml`

Централизованная конфигурация всех инструментов:

**Black (форматирование):**
```toml
[tool.black]
line-length = 127
target-version = ['py310', 'py311', 'py312']
include = '\.pyi?$'
extend-exclude = '''
/(
  | migrations
  | .venv
  | build
  | dist
)/
'''
```

**isort (импорты):**
```toml
[tool.isort]
profile = "black"
line_length = 127
skip_gitignore = true
```

**MyPy (типы):**
```toml
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tests.*"
ignore_errors = true
```

**Pytest (тесты):**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = [
    "-v",
    "--strict-markers",
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-fail-under=80"
]
```

**Coverage:**
```toml
[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/migrations/*"
]
```

#### `.flake8`

Настройки линтера:
```ini
[flake8]
max-line-length = 127
max-complexity = 10
extend-ignore = E203, E266, E501, W503
exclude =
    .git,
    __pycache__,
    .venv,
    venv,
    migrations,
    build,
    dist
```

#### `pytest.ini`

Дополнительные настройки pytest:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    slow: marks tests as slow
    unit: marks tests as unit tests
    integration: marks tests as integration tests
```

### Makefile

Удобные команды для CI/CD:

```makefile
# Основные команды
make help              # Показать все доступные команды
make ci                # Запустить все CI проверки

# Тестирование
make test              # Запустить тесты
make test-cov          # Тесты с покрытием
make test-parallel     # Параллельные тесты
make test-quick        # Быстрые тесты
make coverage-report   # HTML отчет

# Качество кода
make format            # Автоформатирование
make format-check      # Проверка форматирования
make lint              # Линтинг
make type-check        # Проверка типов
make security          # Сканирование безопасности
make complexity        # Анализ сложности

# Установка
make install           # Установить зависимости
make install-dev       # Установить dev зависимости
make install-pre-commit # Установить pre-commit hooks

# Очистка
make clean             # Удалить артефакты
make clean-pyc         # Удалить .pyc файлы
make clean-test        # Удалить test артефакты
```

### Docker для тестирования

#### `Dockerfile.test`

Изолированный контейнер для запуска тестов:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-test.txt

# Копирование кода
COPY src/ src/
COPY tests/ tests/
COPY pytest.ini pyproject.toml ./

# Запуск тестов
CMD ["pytest", "tests/", "--cov=src", "--cov-report=term-missing"]
```

**Использование:**
```bash
# Собрать образ
docker build -t topshort-test -f Dockerfile.test .

# Запустить тесты
docker run --rm topshort-test
```

### Скрипты автоматизации

#### `scripts/setup_ci.sh`

Автоматическая настройка CI/CD окружения:

**Что делает:**
1. Проверяет наличие Python 3.10+
2. Создает виртуальное окружение `.venv`
3. Устанавливает зависимости из requirements.txt и requirements-test.txt
4. Устанавливает pre-commit hooks
5. Создает .gitignore (если отсутствует)
6. Запускает первичные проверки

**Запуск:**
```bash
./scripts/setup_ci.sh
```

#### `scripts/run_ci_locally.sh`

Запуск всех CI проверок локально (идентично GitHub Actions):

**Проверки:**
1. Форматирование (Black, isort)
2. Линтинг (Flake8)
3. Проверка типов (MyPy)
4. Безопасность (Bandit)
5. Тесты с покрытием (Pytest)

**Запуск:**
```bash
./scripts/run_ci_locally.sh
```

## 🚀 Локальная разработка

### Начальная настройка

```bash
# 1. Клонировать репозиторий
git clone https://github.com/YOUR_USERNAME/topshort.git
cd topshort

# 2. Автоматическая настройка
./scripts/setup_ci.sh

# 3. Активировать окружение
source .venv/bin/activate

# 4. Проверить что все работает
make ci
```

### Ежедневное использование

**Перед началом работы:**
```bash
source .venv/bin/activate
```

**Перед коммитом:**
```bash
# Вариант 1: Pre-commit hooks сделают автоматически
git add .
git commit -m "your message"

# Вариант 2: Запустить вручную
make ci
git add .
git commit -m "your message"
```

**Перед созданием PR:**
```bash
./scripts/run_ci_locally.sh
git push origin your-branch
```

## 🔧 Запуск проверок

### Все проверки сразу

```bash
make ci
```

Эквивалентно:
```bash
make clean
make lint
make type-check
make security
make test-cov
```

### Отдельные проверки

```bash
# Форматирование
black src tests                    # Отформатировать
black --check src tests            # Только проверка
make format                        # Через Makefile

# Импорты
isort src tests                    # Отсортировать
isort --check-only src tests       # Только проверка

# Линтинг
flake8 src tests
make lint

# Типы
mypy src --ignore-missing-imports
make type-check

# Безопасность
bandit -r src -ll
make security

# Тесты
pytest tests/
pytest tests/ --cov=src
make test
make test-cov
```

## 📊 Покрытие кода

### Локальный просмотр

```bash
# Генерировать HTML отчет
make coverage-report

# Откроется в браузере: htmlcov/index.html

# Терминал
pytest tests/ --cov=src --cov-report=term-missing
```

### Codecov

**Настройка:**
1. Зарегистрируйтесь на https://codecov.io
2. Подключите GitHub репозиторий
3. Coverage автоматически загружается при каждом CI run

**Badge:**
```markdown
[![codecov](https://codecov.io/gh/USERNAME/topshort/branch/main/graph/badge.svg)](https://codecov.io/gh/USERNAME/topshort)
```

**Конфигурация (`.codecov.yml`):**
```yaml
coverage:
  status:
    project:
      default:
        target: 80%
        threshold: 1%
    patch:
      default:
        target: 80%
```

## 🎨 Стандарты качества кода

### Форматирование
- **Line length:** 127 символов
- **Стиль:** Black (PEP 8 compliant)
- **Импорты:** isort с Black profile

### Линтинг
- **Max complexity:** 10
- **Стиль:** Flake8 с игнорированием Black-конфликтующих правил

### Типизация
- **Strict mode:** на src/
- **Relaxed mode:** на tests/
- **Игнорировать missing imports:** да

### Безопасность
- **Severity:** Low и выше
- **Игнорировать:** тесты и временные файлы

## 🚦 CI/CD Pipeline Flow

```
┌─────────────────┐
│   Push/PR       │
└────────┬────────┘
         │
         ├─────────────────┬─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Tests     │  │Code Quality │  │  Security   │
│   Workflow  │  │   Workflow  │  │    Scans    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       │  Matrix:       │  Checks:       │  Scans:
       │  • Python 3.10 │  • Black       │  • Bandit
       │  • Python 3.11 │  • isort       │  • Safety
       │  • Python 3.12 │  • Flake8      │
       │                │  • MyPy        │
       ▼                ▼                ▼
┌──────────────────────────────────────────┐
│         All Checks Pass?                 │
│                                          │
│  ✓ Python 3.10 Tests                    │
│  ✓ Python 3.11 Tests                    │
│  ✓ Python 3.12 Tests                    │
│  ✓ Coverage ≥ 80%                       │
│  ✓ Code Formatting                      │
│  ✓ Linting                              │
│  ✓ Type Checking                        │
│  ✓ Security                             │
└───────────┬──────────────────────────────┘
            │
            ├─── YES ──→ ✓ Merge Allowed
            │              │
            │              ▼
            │         ┌─────────┐
            │         │ Deploy  │
            │         └─────────┘
            │
            └─── NO ──→ ✗ Merge Blocked
```

## 🐛 Troubleshooting

### Тесты падают локально, но проходят в CI

```bash
# Проверьте версию Python
python --version

# Убедитесь что в виртуальном окружении
which python

# Очистите кеш
make clean

# Переустановите зависимости
pip install -r requirements.txt -r requirements-test.txt

# Запустите снова
make test-cov
```

### Pre-commit хуки слишком медленные

**Решение 1:** Пропустить pytest при коммите
```bash
SKIP=pytest git commit -m "message"
```

**Решение 2:** Отключить pytest в pre-commit
Отредактируйте `.pre-commit-config.yaml`:
```yaml
# - repo: local
#   hooks:
#     - id: pytest
```

### MyPy ошибки

```bash
# Установить type stubs
mypy --install-types

# Или добавить в pyproject.toml:
# ignore_missing_imports = true
```

### Coverage ниже порога

```bash
# Детальный отчет
pytest --cov=src --cov-report=term-missing

# HTML отчет для детального анализа
make coverage-report
```

### GitHub Actions падают

1. Проверьте логи на GitHub → Actions
2. Воспроизведите локально: `make ci`
3. Убедитесь что все зависимости в requirements.txt
4. Проверьте версию Python

## 📈 Best Practices

### Коммиты

```bash
# 1. Запустить проверки
make ci

# 2. Закоммитить
git add .
git commit -m "feat: add new feature"

# 3. Push
git push
```

### Pull Requests

```bash
# 1. Полная проверка
./scripts/run_ci_locally.sh

# 2. Проверить coverage
make coverage-report

# 3. Создать PR
git push origin feature-branch
```

### Поддержка быстрого CI

- ✅ Используйте кеширование зависимостей
- ✅ Запускайте тесты параллельно (`-n auto`)
- ✅ Используйте matrix для разных Python версий
- ✅ Пропускайте медленные тесты в pre-commit

## 🎯 Критерии успешного CI

CI считается успешным когда:

1. ✅ Все тесты прошли на всех Python версиях (3.10, 3.11, 3.12)
2. ✅ Покрытие кода ≥ 80%
3. ✅ Нет ошибок линтинга (Flake8)
4. ✅ Код правильно отформатирован (Black, isort)
5. ✅ Нет ошибок типизации (MyPy)
6. ✅ Нет уязвимостей безопасности (Bandit)
7. ✅ Нет уязвимых зависимостей (Safety)
8. ✅ Сложность кода приемлема (Radon)

## 🔗 Полезные ссылки

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Pytest Documentation](https://docs.pytest.org/)
- [Pre-commit Documentation](https://pre-commit.com/)
- [Codecov Documentation](https://docs.codecov.com/)
- [Black Documentation](https://black.readthedocs.io/)
- [MyPy Documentation](https://mypy.readthedocs.io/)
- [Flake8 Documentation](https://flake8.pycqa.org/)

## 📞 Поддержка

Если возникли проблемы:

1. Проверьте раздел [Troubleshooting](#-troubleshooting)
2. Изучите логи GitHub Actions
3. Запустите проверки локально для воспроизведения
4. Проверьте конфигурационные файлы

## 🎉 Итоги

Ваш CI/CD pipeline настроен для:

- ✅ **Автоматического тестирования** каждого изменения
- ✅ **Поддержки качества кода** с автоматическими проверками
- ✅ **Раннего обнаружения багов** до попадания в production
- ✅ **Обеспечения безопасности** со сканированием уязвимостей
- ✅ **Отслеживания покрытия** с детальными отчетами
- ✅ **Соблюдения стандартов** через pre-commit hooks
- ✅ **Поддержки нескольких версий Python** (3.10, 3.11, 3.12)

**Разработка с уверенностью! 🚀**

---

*Последнее обновление: 2025-01-18*
