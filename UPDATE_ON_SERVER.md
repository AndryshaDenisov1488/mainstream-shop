# Как обновить файлы на сервере из Git

## Быстрая инструкция

### 1. Подключитесь к серверу

```bash
ssh root@mainstreamfs.ru
# или
ssh ваш_пользователь@mainstreamfs.ru
```

### 2. Перейдите в директорию приложения

```bash
cd /root/mainstreamfs.ru
# или если вы используете другого пользователя:
cd ~/mainstreamfs.ru
```

### 3. Проверьте текущий статус

```bash
git status
```

### 4. Получите обновления из Git

```bash
git pull origin main
```

Если возникнут конфликты, Git сообщит об этом. Обычно это не происходит, если вы не редактировали файлы напрямую на сервере.

### 5. Сделайте скрипты исполняемыми (если нужно)

```bash
chmod +x check_static_files.sh
chmod +x fix_static_files.sh
```

### 6. Готово! Теперь можно использовать новые скрипты

```bash
# Запустить диагностику
./check_static_files.sh

# Или исправить проблемы
sudo ./fix_static_files.sh
```

---

## Полная последовательность команд (скопируйте и выполните)

```bash
# 1. Подключение к серверу
ssh root@mainstreamfs.ru

# 2. Переход в директорию
cd /root/mainstreamfs.ru

# 3. Проверка статуса
git status

# 4. Получение обновлений
git pull origin main

# 5. Делаем скрипты исполняемыми
chmod +x check_static_files.sh fix_static_files.sh

# 6. Проверяем, что файлы на месте
ls -la check_static_files.sh fix_static_files.sh STATIC_FILES_TROUBLESHOOTING.md
```

---

## Если Git запросит пароль или логин

Если репозиторий приватный, может потребоваться аутентификация:

### Вариант 1: Использовать SSH ключ (рекомендуется)
```bash
# На сервере проверьте наличие SSH ключа
ls -la ~/.ssh/id_rsa.pub

# Если ключа нет, создайте его
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Добавьте публичный ключ в GitHub:
# Settings → SSH and GPG keys → New SSH key
cat ~/.ssh/id_rsa.pub
```

### Вариант 2: Использовать Personal Access Token
```bash
# При запросе пароля используйте Personal Access Token из GitHub
# Settings → Developer settings → Personal access tokens → Tokens (classic)
```

### Вариант 3: Изменить URL на SSH
```bash
# Проверьте текущий remote URL
git remote -v

# Если это HTTPS, измените на SSH
git remote set-url origin git@github.com:AndryshaDenisov1488/mainstream-shop.git
```

---

## Если возникли конфликты

Если Git сообщит о конфликтах:

```bash
# Посмотреть конфликтующие файлы
git status

# Вариант 1: Оставить версию с сервера (если вы не редактировали на сервере)
git checkout --ours <файл>

# Вариант 2: Взять версию из Git (рекомендуется)
git checkout --theirs <файл>

# Вариант 3: Вручную разрешить конфликт
nano <файл>  # отредактируйте файл, удалив маркеры конфликта

# После разрешения конфликтов
git add .
git commit -m "Разрешены конфликты"
```

---

## Проверка после обновления

```bash
# Проверить, что новые файлы на месте
ls -la check_static_files.sh fix_static_files.sh STATIC_FILES_TROUBLESHOOTING.md

# Проверить версию (последний коммит)
git log -1

# Запустить диагностику статических файлов
./check_static_files.sh
```

---

## Автоматическое обновление (опционально)

Если хотите автоматизировать обновление, можно создать скрипт:

```bash
# Создать файл update.sh
nano /root/mainstreamfs.ru/update.sh
```

Содержимое:
```bash
#!/bin/bash
cd /root/mainstreamfs.ru
git pull origin main
chmod +x check_static_files.sh fix_static_files.sh
echo "✅ Обновление завершено"
```

Сделать исполняемым:
```bash
chmod +x /root/mainstreamfs.ru/update.sh
```

Теперь можно просто запускать:
```bash
./update.sh
```

