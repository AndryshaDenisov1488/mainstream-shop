#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Скрипт для исправления проблем со статическими файлами
# ═══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════════"
echo "Исправление проблем со статическими файлами"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Путь к приложению
APP_PATH="/root/mainstreamfs.ru"
STATIC_PATH="$APP_PATH/app/static"

# Определение пользователя nginx
if id "www-data" &>/dev/null; then
    NGINX_USER="www-data"
elif id "nginx" &>/dev/null; then
    NGINX_USER="nginx"
else
    NGINX_USER=$(ps aux | grep -E '[n]ginx' | head -1 | awk '{print $1}' || echo "www-data")
fi

echo "Пользователь Nginx: $NGINX_USER"
echo ""

# 1. Создание директорий, если их нет
echo "1. Создание директорий..."
mkdir -p "$STATIC_PATH/css"
mkdir -p "$STATIC_PATH/js"
mkdir -p "$STATIC_PATH/images"
echo "✓ Директории созданы"

# 2. Установка прав доступа
echo ""
echo "2. Установка прав доступа..."
chmod -R 755 "$STATIC_PATH"
find "$STATIC_PATH" -type f -exec chmod 644 {} \;
echo "✓ Права установлены"

# 3. Установка владельца
echo ""
echo "3. Установка владельца..."
if [ "$EUID" -eq 0 ]; then
    chown -R "$NGINX_USER:$NGINX_USER" "$STATIC_PATH"
    echo "✓ Владелец установлен: $NGINX_USER"
else
    echo "⚠ Требуются права root для изменения владельца"
    echo "   Выполните: sudo chown -R $NGINX_USER:$NGINX_USER $STATIC_PATH"
fi

# 4. Проверка конфигурации Nginx
echo ""
echo "4. Проверка конфигурации Nginx..."
NGINX_CONFIG="/etc/nginx/sites-available/mainstreamfs.ru"
if [ -f "$NGINX_CONFIG" ]; then
    NGINX_STATIC_PATH=$(grep -A 2 "location /static/" "$NGINX_CONFIG" | grep "alias" | awk '{print $2}' | sed 's/;$//')
    if [ -n "$NGINX_STATIC_PATH" ]; then
        echo "   Путь в Nginx: $NGINX_STATIC_PATH"
        echo "   Реальный путь: $STATIC_PATH"
        
        if [ "$NGINX_STATIC_PATH" != "$STATIC_PATH" ]; then
            echo "⚠ Пути не совпадают!"
            echo "   Обновите конфигурацию Nginx или создайте симлинк"
        else
            echo "✓ Пути совпадают"
        fi
    fi
fi

# 5. Тестирование конфигурации Nginx
echo ""
echo "5. Тестирование конфигурации Nginx..."
if sudo nginx -t 2>/dev/null; then
    echo "✓ Конфигурация Nginx корректна"
    echo ""
    read -p "Перезагрузить Nginx? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl reload nginx
        echo "✓ Nginx перезагружен"
    fi
else
    echo "✗ Ошибка в конфигурации Nginx"
    echo "   Проверьте конфигурацию: sudo nginx -t"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Готово! Теперь запустите check_static_files.sh для проверки"
echo "═══════════════════════════════════════════════════════════════"

