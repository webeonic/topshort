# Deployment Guide - Digital Ocean

Полное руководство по развертыванию TopShort на Digital Ocean с автоматическим CI/CD.

## Архитектура деплоя

```
GitHub Repository
       ↓
  Push to main
       ↓
GitHub Actions (CI/CD)
       ↓
   SSH Deploy
       ↓
Digital Ocean Droplet
       ↓
   Docker Container
       ↓
  TopShort Bot Running
```

## Часть 1: Создание Digital Ocean Droplet

### 1. Создайте Droplet

1. Войдите в Digital Ocean: https://cloud.digitalocean.com/
2. Create → Droplets
3. Выберите конфигурацию:
   - **Image**: Ubuntu 22.04 LTS
   - **Plan**: Basic
   - **CPU**: Regular (1GB RAM / 1 CPU) - достаточно для начала
   - **Datacenter**: выберите ближайший
   - **Authentication**: SSH Key (создайте или используйте существующий)
   - **Hostname**: topshort-bot

4. Create Droplet

### 2. Подключитесь к серверу

```bash
ssh root@your_droplet_ip
```

### 3. Установите Docker

```bash
# Обновите систему
apt update && apt upgrade -y

# Установите Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Установите Docker Compose
apt install docker-compose -y

# Проверьте установку
docker --version
docker-compose --version
```

### 4. Настройте пользователя (опционально, для безопасности)

```bash
# Создайте нового пользователя
adduser deployer
usermod -aG sudo deployer
usermod -aG docker deployer

# Настройте SSH для нового пользователя
mkdir -p /home/deployer/.ssh
cp /root/.ssh/authorized_keys /home/deployer/.ssh/
chown -R deployer:deployer /home/deployer/.ssh
chmod 700 /home/deployer/.ssh
chmod 600 /home/deployer/.ssh/authorized_keys

# Используйте deployer вместо root далее
```

### 5. Клонируйте репозиторий

```bash
# Создайте директорию
mkdir -p /opt/topshort
cd /opt/topshort

# Клонируйте репозиторий
git clone https://github.com/webeonic/topshort.git .

# Или, если используете приватный репозиторий:
# Сначала добавьте SSH ключ на GitHub
ssh-keygen -t ed25519 -C "deployer@topshort"
cat ~/.ssh/id_ed25519.pub
# Добавьте этот ключ в GitHub: Settings → SSH Keys
git clone git@github.com:webeonic/topshort.git .
```

### 6. Настройте .env файл

```bash
cp .env.example .env
nano .env
```

Заполните все необходимые переменные:
```bash
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=false  # false для продакшена

TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Настройте параметры торговли
MARGIN_PER_TRADE=100.0
MAX_POSITIONS=10
DEFAULT_LEVERAGE=20
# и т.д.
```

### 7. Запустите бота вручную (первый раз)

```bash
# Соберите образ
docker-compose build

# Запустите
docker-compose up -d

# Проверьте логи
docker-compose logs -f

# Проверьте статус
docker-compose ps
```

## Часть 2: Настройка GitHub Actions CI/CD

### 1. Создайте SSH ключ для GitHub Actions

На вашем Droplet:

```bash
# Создайте новый SSH ключ специально для CI/CD
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions_key -N ""

# Добавьте публичный ключ в authorized_keys
cat ~/.ssh/github_actions_key.pub >> ~/.ssh/authorized_keys

# Скопируйте приватный ключ (понадобится для GitHub)
cat ~/.ssh/github_actions_key
```

### 2. Настройте GitHub Secrets

Перейдите в ваш репозиторий на GitHub:
- Settings → Secrets and variables → Actions → New repository secret

Добавьте следующие секреты:

| Secret Name | Value | Описание |
|-------------|-------|----------|
| `DO_SSH_PRIVATE_KEY` | Содержимое `~/.ssh/github_actions_key` | Приватный SSH ключ |
| `DO_HOST` | IP адрес вашего Droplet | Например: 164.90.xxx.xxx |
| `DO_USER` | `root` или `deployer` | Пользователь для SSH |

### 3. Тестируйте CI/CD

```bash
# Сделайте любое изменение и запушьте
git add .
git commit -m "test: CI/CD deployment"
git push origin main
```

Проверьте:
- GitHub → Actions → Должен запуститься workflow "Deploy to Digital Ocean"
- Если все зеленое ✅ - деплой прошел успешно

## Часть 3: Управление ботом на сервере

### Основные команды

```bash
# Подключитесь к серверу
ssh root@your_droplet_ip
cd /opt/topshort

# Посмотреть логи
docker-compose logs -f
docker-compose logs -f --tail=100

# Перезапустить бота
docker-compose restart

# Остановить бота
docker-compose down

# Запустить бота
docker-compose up -d

# Посмотреть статус
docker-compose ps

# Обновить код вручную
git pull origin main
docker-compose build
docker-compose up -d

# Зайти внутрь контейнера
docker-compose exec topshort /bin/bash
```

### Мониторинг

```bash
# Проверка ресурсов
docker stats

# Логи в реальном времени
docker-compose logs -f

# Последние 100 строк
docker-compose logs --tail=100

# Поиск ошибок
docker-compose logs | grep ERROR
```

## Часть 4: Безопасность

### 1. Настройте файрвол

```bash
# Разрешите только SSH
ufw allow 22/tcp
ufw enable

# Проверьте статус
ufw status
```

### 2. Измените SSH порт (опционально)

```bash
# Отредактируйте конфигурацию SSH
nano /etc/ssh/sshd_config

# Измените порт (например, на 2222)
Port 2222

# Перезапустите SSH
systemctl restart sshd

# Обновите файрвол
ufw allow 2222/tcp
ufw delete allow 22/tcp
```

### 3. Ограничьте доступ к .env

```bash
chmod 600 /opt/topshort/.env
```

### 4. Настройте автоматические обновления

```bash
apt install unattended-upgrades -y
dpkg-reconfigure --priority=low unattended-upgrades
```

## Часть 5: Backup и восстановление

### Backup базы данных

```bash
# Создайте скрипт backup
cat > /opt/topshort/backup.sh << 'SCRIPT'
#!/bin/bash
BACKUP_DIR="/opt/topshort/backups"
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d_%H%M%S)
cp /opt/topshort/data/topshort.db $BACKUP_DIR/backup_$DATE.db
# Удалите старые бэкапы (старше 7 дней)
find $BACKUP_DIR -name "backup_*.db" -mtime +7 -delete
SCRIPT

chmod +x /opt/topshort/backup.sh
```

### Автоматический backup через cron

```bash
# Откройте crontab
crontab -e

# Добавьте строку (backup каждый день в 3:00)
0 3 * * * /opt/topshort/backup.sh
```

### Восстановление

```bash
# Остановите бота
docker-compose down

# Восстановите базу
cp /opt/topshort/backups/backup_YYYYMMDD_HHMMSS.db /opt/topshort/data/topshort.db

# Запустите бота
docker-compose up -d
```

## Часть 6: Масштабирование

### Увеличение ресурсов Droplet

1. Digital Ocean Dashboard → Droplet → Resize
2. Выберите больший план
3. Resize Droplet
4. Перезапустите бота

### Мониторинг производительности

```bash
# Установите мониторинг
apt install htop iotop -y

# Смотрите нагрузку
htop

# Смотрите использование Docker
docker stats
```

## Часть 7: Troubleshooting

### Бот не запускается

```bash
# Проверьте логи
docker-compose logs --tail=100

# Проверьте .env файл
cat .env

# Пересоберите контейнер
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### CI/CD не работает

1. Проверьте GitHub Actions logs
2. Проверьте SSH подключение вручную:
   ```bash
   ssh -i ~/.ssh/github_actions_key root@your_droplet_ip
   ```
3. Проверьте GitHub Secrets

### Бот работает, но не торгует

```bash
# Проверьте статус через Telegram
/status
/settings

# Проверьте логи
docker-compose logs -f | grep ERROR
```

## Часть 8: Обновления

### Автоматическое обновление (через GitHub Actions)

Просто запушьте код в main ветку - бот обновится автоматически.

### Ручное обновление

```bash
ssh root@your_droplet_ip
cd /opt/topshort
git pull origin main
docker-compose down
docker-compose build
docker-compose up -d
```

## Полезные команды

```bash
# Очистка диска
docker system prune -a --volumes -f

# Экспорт логов
docker-compose logs > logs_$(date +%Y%m%d).txt

# Проверка версии
docker-compose exec topshort python -c "import ccxt; print(ccxt.__version__)"

# Restart всей системы
reboot
```

## Стоимость

Примерная стоимость на Digital Ocean:
- **Basic Droplet (1GB RAM)**: $6/месяц
- **Basic Droplet (2GB RAM)**: $12/месяц (рекомендуется)
- **Backup**: +$1.20/месяц (20% от стоимости Droplet)

**Итого**: ~$13/месяц для стабильной работы

## Поддержка

- Логи: `docker-compose logs -f`
- Telegram: команда `/status`
- GitHub Issues: https://github.com/webeonic/topshort/issues

---

**Готово! Ваш бот теперь работает 24/7 на Digital Ocean с автоматическим CI/CD! 🚀**
