#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Скрипт запуска MainStream Shop с платежами на production
# ═══════════════════════════════════════════════════════════════

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  MainStream Shop с платежами - Запуск Production${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"

# Получаем директорию скрипта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Виртуальное окружение не найдено!${NC}"
    echo -e "${YELLOW}Создайте его командой: python3 -m venv venv${NC}"
    exit 1
fi

# Активация виртуального окружения
echo -e "${YELLOW}🔄 Активация виртуального окружения...${NC}"
source venv/bin/activate

# Создание необходимых директорий
echo -e "${YELLOW}📁 Создание директорий...${NC}"
mkdir -p logs
mkdir -p uploads
mkdir -p instance
mkdir -p uploads/chat
mkdir -p uploads/xml

# Проверка зависимостей
echo -e "${YELLOW}📦 Проверка зависимостей...${NC}"
pip install -q -r requirements.txt

# Инициализация базы данных (если нужно)
if [ ! -f "instance/app.db" ]; then
    echo -e "${YELLOW}🗄️  Инициализация базы данных...${NC}"
    python3 create_database_final.py
fi

# Остановка предыдущего процесса (если есть)
if [ -f "logs/gunicorn.pid" ]; then
    echo -e "${YELLOW}🛑 Остановка предыдущего процесса...${NC}"
    kill $(cat logs/gunicorn.pid) 2>/dev/null || true
    sleep 2
fi

# Запуск Gunicorn
echo -e "${GREEN}🚀 Запуск Gunicorn...${NC}"
gunicorn -c gunicorn_config.py wsgi:application &

# Ожидание запуска
sleep 3

# Проверка запуска
if [ -f "logs/gunicorn.pid" ]; then
    PID=$(cat logs/gunicorn.pid)
    if ps -p $PID > /dev/null; then
        echo -e "${GREEN}✅ Сервер успешно запущен! PID: $PID${NC}"
        echo -e "${GREEN}📊 Логи: logs/gunicorn_access.log${NC}"
        echo -e "${GREEN}❌ Ошибки: logs/gunicorn_error.log${NC}"
        echo -e "${GREEN}💳 Платежи: CloudPayments интегрированы${NC}"
    else
        echo -e "${RED}❌ Ошибка запуска сервера${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Файл PID не создан${NC}"
    exit 1
fi

echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"