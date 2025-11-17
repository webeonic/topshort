# SSH Setup для GitHub Actions

Пошаговая инструкция по настройке SSH ключей для автоматического деплоя.

## Проблема: Exit code 255

Ошибка 255 означает проблему с SSH подключением. Вот как это исправить:

## Шаг 1: Подключитесь к серверу

```bash
ssh root@YOUR_DROPLET_IP
```

## Шаг 2: Создайте новый SSH ключ для CI/CD

```bash
# Создайте ключ специально для GitHub Actions
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions -N ""

# Добавьте публичный ключ в authorized_keys
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys

# Проверьте права доступа
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
chmod 600 ~/.ssh/github_actions
chmod 644 ~/.ssh/github_actions.pub
```

## Шаг 3: Скопируйте приватный ключ

```bash
cat ~/.ssh/github_actions
```

Вы должны увидеть что-то вроде:

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtz
...много строк...
AAAAAEC5AAAAAAAAAQAAAA==
-----END OPENSSH PRIVATE KEY-----
```

**ВАЖНО**: Скопируйте ВЕСЬ текст, включая строки `-----BEGIN` и `-----END`

## Шаг 4: Добавьте в GitHub Secrets

1. Перейдите в ваш репозиторий на GitHub
2. Settings → Secrets and variables → Actions
3. Нажмите "New repository secret"

### Добавьте 3 секрета:

#### 1. DO_SSH_PRIVATE_KEY
```
Вставьте ВЕСЬ приватный ключ из предыдущего шага
```

#### 2. DO_HOST
```
IP адрес вашего Droplet (например: 164.90.123.45)
```

#### 3. DO_USER
```
root
```
(или `deployer`, если вы создали отдельного пользователя)

## Шаг 5: Тест SSH подключения вручную

На вашем локальном компьютере:

```bash
# Сохраните ключ локально для теста
echo "YOUR_PRIVATE_KEY_HERE" > /tmp/test_key
chmod 600 /tmp/test_key

# Попробуйте подключиться
ssh -i /tmp/test_key root@YOUR_DROPLET_IP "echo 'Connection successful!'"

# Удалите тестовый ключ
rm /tmp/test_key
```

Если это работает, значит ключ правильный.

## Шаг 6: Запустите деплой

После добавления секретов, запустите деплой:

1. GitHub → Actions
2. Deploy to Digital Ocean → Run workflow
3. Или просто сделайте push в main ветку

## Troubleshooting

### Ошибка "Permission denied (publickey)"

Проверьте:
```bash
# На сервере
cat ~/.ssh/authorized_keys | grep github-actions
# Должна быть строка с вашим публичным ключом
```

### Ошибка "bad permissions"

```bash
# На сервере
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### Ключ выглядит странно

Приватный ключ должен:
- ✅ Начинаться с `-----BEGIN OPENSSH PRIVATE KEY-----`
- ✅ Заканчиваться с `-----END OPENSSH PRIVATE KEY-----`
- ✅ Содержать только base64 символы между BEGIN и END
- ❌ НЕ содержать комментариев
- ❌ НЕ содержать лишних пробелов/переносов строк в начале/конце

### Проверка формата ключа

```bash
# На сервере
head -1 ~/.ssh/github_actions
# Должно быть: -----BEGIN OPENSSH PRIVATE KEY-----

tail -1 ~/.ssh/github_actions
# Должно быть: -----END OPENSSH PRIVATE KEY-----

wc -l ~/.ssh/github_actions
# Обычно 7-10 строк для ed25519 ключа
```

## Альтернатива: Использование существующего ключа

Если у вас уже есть SSH ключ для доступа к серверу:

```bash
# На вашем локальном компьютере
cat ~/.ssh/id_ed25519
# или
cat ~/.ssh/id_rsa

# Скопируйте этот ключ и добавьте в DO_SSH_PRIVATE_KEY
```

Но убедитесь, что соответствующий публичный ключ есть в `~/.ssh/authorized_keys` на сервере!

## Проверка GitHub Actions логов

После запуска деплоя, проверьте логи:

1. GitHub → Actions → последний запуск
2. Раскройте "Setup SSH"
3. Должно быть:
   ```
   🔍 Checking SSH key...
   -----BEGIN OPENSSH PRIVATE KEY-----
   -----END OPENSSH PRIVATE KEY-----
   7 ~/.ssh/deploy_key
   ```

4. Раскройте "Test SSH Connection"
5. Должно быть:
   ```
   🔌 Testing SSH connection to root@YOUR_IP...
   ✅ SSH connection successful!
   ```

Если тест успешен, но деплой падает дальше - проблема не в SSH, а в чем-то другом.

## Быстрый чеклист

- [ ] SSH ключ создан на сервере
- [ ] Публичный ключ добавлен в authorized_keys
- [ ] Права 700 на ~/.ssh, 600 на authorized_keys
- [ ] Приватный ключ скопирован ПОЛНОСТЬЮ (включая BEGIN/END)
- [ ] Секрет DO_SSH_PRIVATE_KEY добавлен в GitHub
- [ ] Секрет DO_HOST содержит правильный IP
- [ ] Секрет DO_USER содержит правильное имя пользователя
- [ ] Тест SSH подключения проходит успешно

---

**Если все еще не работает**, пришлите скриншот логов из GitHub Actions (шаги "Setup SSH" и "Test SSH Connection").
