# CI/CD - Быстрый старт

## ⚡ Установка за 1 команду

```bash
./scripts/setup_ci.sh
```

Эта команда автоматически:
- ✅ Создаст виртуальное окружение `.venv`
- ✅ Установит все зависимости для разработки и тестирования
- ✅ Настроит pre-commit хуки
- ✅ Запустит первичные проверки
- ✅ Создаст .gitignore (если нужно)

## 🚀 Активация и проверка

```bash
# 1. Активируйте виртуальное окружение
source .venv/bin/activate

# 2. Проверьте что все работает
make ci

# Если все прошло успешно:
# ✓ All CI checks passed!
```

## 📋 Основные команды

### Тестирование

```bash
make test              # Запустить тесты
make test-cov          # Тесты с отчетом покрытия
make test-parallel     # Параллельные тесты (быстрее)
make coverage-report   # Открыть HTML отчет
```

### Проверка качества кода

```bash
make format            # Автоматически отформатировать код
make format-check      # Проверить форматирование
make lint              # Запустить линтер
make type-check        # Проверить типы
make security          # Сканирование безопасности
```

### Комплексная проверка

```bash
make ci                # Запустить ВСЕ проверки (как на GitHub)
./scripts/run_ci_locally.sh  # Альтернативный способ
```

### Очистка

```bash
make clean             # Удалить артефакты (кеш, coverage и т.д.)
```

## 🔄 Рабочий процесс

### Перед каждым коммитом

**Автоматически** (через pre-commit hooks):
```bash
git add .
git commit -m "your message"
# Pre-commit хуки автоматически:
# ✓ отформатируют код
# ✓ проверят линтером
# ✓ проверят типы
# ✓ просканируют на уязвимости
# ✓ запустят тесты
```

**Вручную** (если нужно проверить заранее):
```bash
make ci
git add .
git commit -m "your message"
```

### Перед push в GitHub

```bash
# Убедитесь что все проверки проходят
make ci

# Если все ОК - можно push
git push origin main
```

### Пропустить pre-commit хуки (когда очень срочно)

```bash
git commit --no-verify -m "urgent fix"
```

## 🎯 Что происходит на GitHub после push

### 1. Tests Workflow
- ✅ Тесты на Python 3.10
- ✅ Тесты на Python 3.11
- ✅ Тесты на Python 3.12
- ✅ Проверка покрытия ≥ 80%
- ✅ Загрузка отчетов на Codecov

### 2. Code Quality Workflow
- ✅ Форматирование (Black, isort)
- ✅ Линтинг (Flake8)
- ✅ Проверка типов (MyPy)
- ✅ Безопасность (Bandit)
- ✅ Уязвимости зависимостей (Safety)

Результаты видны в разделе **Actions** на GitHub.

## 📊 Добавьте бейджи в README

Откройте `README.md` и добавьте в начало:

```markdown
![Tests](https://github.com/YOUR_USERNAME/topshort/actions/workflows/tests.yml/badge.svg)
![Code Quality](https://github.com/YOUR_USERNAME/topshort/actions/workflows/code-quality.yml/badge.svg)
[![codecov](https://codecov.io/gh/YOUR_USERNAME/topshort/branch/main/graph/badge.svg)](https://codecov.io/gh/YOUR_USERNAME/topshort)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
```

*Замените YOUR_USERNAME на ваш GitHub username*

## 🔧 Настройка Codecov (опционально, но рекомендуется)

1. Зарегистрируйтесь на https://codecov.io с GitHub аккаунтом
2. Добавьте репозиторий `topshort`
3. Готово! Coverage будет автоматически загружаться при каждом push
4. Добавьте badge (см. выше)

## 🛡️ Защита main ветки (рекомендуется)

На GitHub Settings → Branches → Add rule:

1. Branch name pattern: `main` (или `master`)
2. ✅ **Require status checks to pass before merging**
3. Выберите проверки:
   - `test (3.10)`
   - `test (3.11)`
   - `test (3.12)`
   - `code-quality`
4. ✅ **Require branches to be up to date before merging**

Теперь merge будет заблокирован если тесты не проходят!

## ❓ Частые вопросы

### Как запустить один конкретный тест?

```bash
pytest tests/test_position_manager.py::TestOpenPosition::test_open_position_success
```

### Тесты проходят локально, но падают на GitHub?

```bash
# Проверьте версию Python
python --version

# Убедитесь что используете виртуальное окружение
source .venv/bin/activate

# Очистите и переустановите
make clean
pip install -r requirements.txt -r requirements-test.txt
make test-cov
```

### Pre-commit хуки слишком медленные?

Отредактируйте `.pre-commit-config.yaml` и закомментируйте pytest:

```yaml
# - repo: local
#   hooks:
#     - id: pytest
```

Или пропустите при коммите:
```bash
SKIP=pytest git commit -m "message"
```

### Как посмотреть детальный отчет о покрытии?

```bash
make coverage-report
# Откроется в браузере: htmlcov/index.html
```

## ✅ Чеклист первого запуска

Проверьте что сделано:

```
☐ Выполнен ./scripts/setup_ci.sh
☐ Активировано виртуальное окружение (.venv)
☐ Выполнен make ci успешно
☐ Тесты запускаются (make test)
☐ Создан/проверен .gitignore
☐ Добавлены бейджи в README.md
☐ Первый коммит с CI/CD сделан
☐ Push на GitHub выполнен
☐ GitHub Actions проверки прошли ✓
☐ Codecov настроен (опционально)
☐ Branch protection включен (опционально)
```

## 📚 Дополнительная документация

- [docs/CI_CD.md](CI_CD.md) - Полная документация CI/CD
- [docs/DEVELOPMENT.md](DEVELOPMENT.md) - Руководство разработчика
- [docs/architecture/TESTING.md](architecture/TESTING.md) - Детали тестирования

## 🎉 Готово!

Теперь ваш проект защищен автоматическими проверками:

✅ **160+ unit tests** с 85-95% покрытием
✅ **Автоматический запуск** при каждом push
✅ **Pre-commit хуки** для локальной проверки
✅ **Проверка качества кода** (форматирование, линтинг, типы)
✅ **Сканирование безопасности** (Bandit, Safety)
✅ **Отчеты о покрытии** на Codecov
✅ **Блокировка merge** при проваленных тестах

**Разработка с уверенностью! 🚀**

---

*Последнее обновление: 2025-01-18*
