#!/bin/bash
# ✅ Скрипт автоматического бэкапа базы данных MainStream Shop
# Запускается через cron каждый день в 00:30
# Хранит бэкапы 14 дней

# Настройки
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/var/backups/mainstream"
DB_PATH="$PROJECT_DIR/instance/app.db"
VENV_PATH="$PROJECT_DIR/venv"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/app_$DATE.db"
LOG_FILE="/var/log/mainstream_backup.log"
RETENTION_DAYS=14

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "Starting database backup"
log "Project directory: $PROJECT_DIR"

# Переходим в директорию проекта
cd "$PROJECT_DIR" || {
    log "ERROR: Cannot change to project directory: $PROJECT_DIR"
    exit 1
}

# Активируем виртуальное окружение (если существует)
if [ -f "$VENV_PATH/bin/activate" ]; then
    log "Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
    log "✅ Virtual environment activated"
else
    log "⚠️ Virtual environment not found at $VENV_PATH, continuing without it"
fi

# Проверяем что база данных существует
if [ ! -f "$DB_PATH" ]; then
    log "ERROR: Database file not found at $DB_PATH"
    exit 1
fi

# Создаем директорию для бэкапов если не существует
if [ ! -d "$BACKUP_DIR" ]; then
    log "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to create backup directory"
        exit 1
    fi
fi

# Проверяем наличие sqlite3
if ! command -v sqlite3 &> /dev/null; then
    log "ERROR: sqlite3 command not found. Please install sqlite3."
    exit 1
fi

# Создаем бэкап используя SQLite backup API
log "Creating backup: $BACKUP_FILE"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

if [ $? -eq 0 ]; then
    log "✅ Backup created successfully"
    
    # Получаем размер файла
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "Backup size: $BACKUP_SIZE"
    
    # Сжимаем бэкап
    log "Compressing backup..."
    gzip "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        COMPRESSED_SIZE=$(du -h "$BACKUP_FILE.gz" | cut -f1)
        log "✅ Backup compressed: $BACKUP_FILE.gz (size: $COMPRESSED_SIZE)"
        
        # Проверяем целостность сжатого файла
        gunzip -t "$BACKUP_FILE.gz" 2>/dev/null
        
        if [ $? -eq 0 ]; then
            log "✅ Backup integrity verified"
        else
            log "ERROR: Backup integrity check failed!"
            exit 1
        fi
    else
        log "ERROR: Failed to compress backup"
        exit 1
    fi
else
    log "ERROR: Failed to create backup"
    exit 1
fi

# Удаляем старые бэкапы (старше RETENTION_DAYS дней)
log "Cleaning up old backups (older than $RETENTION_DAYS days)..."
OLD_BACKUPS=$(find "$BACKUP_DIR" -name "app_*.db.gz" -mtime +$RETENTION_DAYS)

if [ -n "$OLD_BACKUPS" ]; then
    echo "$OLD_BACKUPS" | while read -r old_backup; do
        log "Deleting old backup: $old_backup"
        rm -f "$old_backup"
    done
    log "✅ Old backups cleaned up"
else
    log "No old backups to delete"
fi

# Показываем список всех бэкапов
log "Current backups:"
ls -lh "$BACKUP_DIR"/app_*.db.gz | tail -5 | while read -r line; do
    log "  $line"
done

# Подсчитываем общий размер бэкапов
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Total backup size: $TOTAL_SIZE"

log "Backup completed successfully"
log "========================================="

exit 0

