#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Скрипт для исправления прав доступа для Nginx
# ═══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════════"
echo "Исправление прав доступа для Nginx"
echo "═══════════════════════════════════════════════════════════════"
echo ""

APP_PATH="/root/mainstreamfs.ru"
STATIC_PATH="$APP_PATH/app/static"

# Определение пользователя nginx
if id "www-data" &>/dev/null; then
    NGINX_USER="www-data"
    NGINX_GROUP="www-data"
elif id "nginx" &>/dev/null; then
    NGINX_USER="nginx"
    NGINX_GROUP="nginx"
else
    echo "⚠ Не удалось определить пользователя Nginx"
    echo "Попробуем найти процесс Nginx..."
    NGINX_USER=$(ps aux | grep -E '[n]ginx' | head -1 | awk '{print $1}' || echo "www-data")
    NGINX_GROUP="$NGINX_USER"
fi

echo "Пользователь Nginx: $NGINX_USER:$NGINX_GROUP"
echo ""

# Проверка, что мы root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Этот скрипт должен быть запущен от root (используйте sudo)"
    exit 1
fi

echo "1. Установка прав на родительские директории..."
echo "───────────────────────────────────────────────────────────────"

# Даем права на чтение и выполнение для родительских директорий
# Это нужно, чтобы nginx мог добраться до /root/mainstreamfs.ru/app/static/
chmod 755 /root
chmod 755 /root/mainstreamfs.ru
chmod 755 /root/mainstreamfs.ru/app
echo "✓ Права на родительские директории установлены"

echo ""
echo "2. Установка прав на директорию static..."
echo "───────────────────────────────────────────────────────────────"

# Устанавливаем права на директорию static
chmod 755 "$STATIC_PATH"
find "$STATIC_PATH" -type d -exec chmod 755 {} \;
find "$STATIC_PATH" -type f -exec chmod 644 {} \;
echo "✓ Права на файлы установлены"

echo ""
echo "3. Изменение владельца файлов..."
echo "───────────────────────────────────────────────────────────────"

# Меняем владельца на nginx пользователя
chown -R "$NGINX_USER:$NGINX_GROUP" "$STATIC_PATH"
echo "✓ Владелец изменен на $NGINX_USER:$NGINX_GROUP"

echo ""
echo "4. Проверка результата..."
echo "───────────────────────────────────────────────────────────────"

# Проверяем права
echo "Права на директорию static:"
ls -ld "$STATIC_PATH"
echo ""
echo "Права на файлы:"
ls -la "$STATIC_PATH/css/" | head -3
ls -la "$STATIC_PATH/js/" | head -3
ls -la "$STATIC_PATH/images/" | head -3

echo ""
echo "5. Проверка доступности для nginx..."
echo "───────────────────────────────────────────────────────────────"

# Проверяем, может ли nginx читать файлы
if sudo -u "$NGINX_USER" test -r "$STATIC_PATH/css/main.css"; then
    echo "✓ Nginx может читать CSS файл"
else
    echo "✗ Nginx НЕ может читать CSS файл"
fi

if sudo -u "$NGINX_USER" test -r "$STATIC_PATH/js/main.js"; then
    echo "✓ Nginx может читать JS файл"
else
    echo "✗ Nginx НЕ может читать JS файл"
fi

if sudo -u "$NGINX_USER" test -r "$STATIC_PATH/images/logo.png"; then
    echo "✓ Nginx может читать логотип"
else
    echo "✗ Nginx НЕ может читать логотип"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Готово! Теперь проверьте доступность файлов:"
echo "  curl -I https://mainstreamfs.ru/static/css/main.css"
echo ""
echo "Или запустите: ./check_static_files.sh"
echo "═══════════════════════════════════════════════════════════════"

