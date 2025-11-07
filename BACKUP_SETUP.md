# 💾 Настройка автоматического бэкапа базы данных

## 📋 Описание

Скрипт `backup_database.sh` автоматически создает резервные копии базы данных SQLite:
- ✅ Запускается каждый день в 00:30
- ✅ Сжимает бэкапы (gzip)
- ✅ Проверяет целостность
- ✅ Хранит бэкапы 14 дней
- ✅ Логирует все действия

## 🚀 Установка

### 1. Сделайте скрипт исполняемым

```bash
chmod +x backup_database.sh
```

### 2. Создайте директорию для бэкапов

```bash
sudo mkdir -p /var/backups/mainstream
sudo chown $USER:$USER /var/backups/mainstream
```

### 3. Создайте лог-файл

```bash
sudo touch /var/log/mainstream_backup.log
sudo chown $USER:$USER /var/log/mainstream_backup.log
```

### 4. Протестируйте скрипт вручную

```bash
cd /path/to/mainstream-shop
./backup_database.sh
```

Проверьте что бэкап создан:

```bash
ls -lh /var/backups/mainstream/
cat /var/log/mainstream_backup.log
```

### 5. Настройте cron для автоматического запуска

Откройте crontab:

```bash
crontab -e
```

Добавьте строку (замените `/path/to/mainstream-shop` на реальный путь):

```cron
# Бэкап базы данных MainStream Shop каждый день в 00:30
30 0 * * * cd /path/to/mainstream-shop && ./backup_database.sh >> /var/log/mainstream_backup.log 2>&1
```

Сохраните и закройте редактор.

### 6. Проверьте что cron настроен

```bash
crontab -l
```

Вы должны увидеть добавленную строку.

## 📊 Проверка работы

### Просмотр логов

```bash
tail -f /var/log/mainstream_backup.log
```

### Просмотр бэкапов

```bash
ls -lh /var/backups/mainstream/
```

### Проверка размера бэкапов

```bash
du -sh /var/backups/mainstream/
```

## 🔄 Восстановление из бэкапа

### 1. Найдите нужный бэкап

```bash
ls -lh /var/backups/mainstream/
```

### 2. Распакуйте бэкап

```bash
gunzip /var/backups/mainstream/app_20241107_003000.db.gz
```

### 3. Остановите приложение

```bash
sudo systemctl stop mainstreamfs
```

### 4. Создайте резервную копию текущей БД

```bash
cp instance/app.db instance/app.db.old
```

### 5. Восстановите БД из бэкапа

```bash
cp /var/backups/mainstream/app_20241107_003000.db instance/app.db
```

### 6. Запустите приложение

```bash
sudo systemctl start mainstreamfs
```

### 7. Проверьте работу

```bash
sudo systemctl status mainstreamfs
```

## ⚙️ Настройка параметров

Отредактируйте `backup_database.sh` для изменения параметров:

```bash
# Директория для бэкапов
BACKUP_DIR="/var/backups/mainstream"

# Путь к базе данных
DB_PATH="instance/app.db"

# Сколько дней хранить бэкапы
RETENTION_DAYS=14

# Файл логов
LOG_FILE="/var/log/mainstream_backup.log"
```

## 🔔 Мониторинг бэкапов

### Создайте скрипт проверки последнего бэкапа

```bash
#!/bin/bash
# check_backup.sh

BACKUP_DIR="/var/backups/mainstream"
LAST_BACKUP=$(ls -t "$BACKUP_DIR"/app_*.db.gz 2>/dev/null | head -1)

if [ -z "$LAST_BACKUP" ]; then
    echo "❌ No backups found!"
    exit 1
fi

# Проверяем что последний бэкап не старше 2 дней
BACKUP_AGE=$(find "$LAST_BACKUP" -mtime +2)

if [ -n "$BACKUP_AGE" ]; then
    echo "⚠️ Last backup is older than 2 days: $LAST_BACKUP"
    exit 1
else
    echo "✅ Last backup is recent: $LAST_BACKUP"
    ls -lh "$LAST_BACKUP"
    exit 0
fi
```

Сделайте исполняемым:

```bash
chmod +x check_backup.sh
```

Добавьте в cron для ежедневной проверки:

```cron
# Проверка бэкапов каждый день в 9:00
0 9 * * * /path/to/mainstream-shop/check_backup.sh
```

## 📤 Загрузка бэкапов в облако (опционально)

### Яндекс.Облако (S3)

Установите AWS CLI:

```bash
sudo apt install awscli
```

Настройте credentials:

```bash
aws configure
```

Добавьте в конец `backup_database.sh`:

```bash
# Загружаем в Яндекс.Облако
log "Uploading to Yandex Cloud..."
aws s3 cp "$BACKUP_FILE.gz" s3://mainstream-backups/ \
    --endpoint-url=https://storage.yandexcloud.net

if [ $? -eq 0 ]; then
    log "✅ Backup uploaded to cloud"
else
    log "ERROR: Failed to upload backup to cloud"
fi
```

## 🆘 Troubleshooting

### Ошибка: "Database file not found"

Убедитесь что запускаете скрипт из корня проекта:

```bash
cd /path/to/mainstream-shop
./backup_database.sh
```

### Ошибка: "Permission denied"

Дайте права на выполнение:

```bash
chmod +x backup_database.sh
```

И проверьте права на директории:

```bash
sudo chown -R $USER:$USER /var/backups/mainstream
sudo chown $USER:$USER /var/log/mainstream_backup.log
```

### Ошибка: "sqlite3 command not found"

Установите sqlite3:

```bash
sudo apt install sqlite3
```

### Cron не запускается

Проверьте синтаксис в crontab:

```bash
crontab -l
```

Проверьте логи cron:

```bash
sudo tail -f /var/log/syslog | grep CRON
```

## 📝 Примечания

- Бэкапы создаются с использованием SQLite `.backup` API, что гарантирует консистентность даже при работающем приложении
- Сжатие gzip экономит ~70-80% места
- Автоматическая очистка старых бэкапов предотвращает переполнение диска
- Все действия логируются для отладки

---

**Дата создания:** 7 ноября 2024  
**Версия:** 1.0

