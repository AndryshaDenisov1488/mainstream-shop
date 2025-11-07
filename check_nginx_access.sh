#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Скрипт для проверки доступа Nginx к файлам
# ═══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════════"
echo "Проверка доступа Nginx к статическим файлам"
echo "═══════════════════════════════════════════════════════════════"
echo ""

APP_PATH="/root/mainstreamfs.ru"
STATIC_PATH="$APP_PATH/app/static"

# Определение пользователя nginx worker процессов
NGINX_USER=$(ps aux | grep '[n]ginx: worker' | head -1 | awk '{print $1}' || echo "www-data")
echo "Пользователь Nginx worker: $NGINX_USER"
echo ""

echo "1. Проверка прав на родительские директории..."
echo "───────────────────────────────────────────────────────────────"

# Проверка /root
ROOT_PERMS=$(stat -c "%a" /root 2>/dev/null || stat -f "%OLp" /root 2>/dev/null)
ROOT_OWNER=$(stat -c "%U:%G" /root 2>/dev/null || stat -f "%Su:%Sg" /root 2>/dev/null)
echo "  /root: права=$ROOT_PERMS, владелец=$ROOT_OWNER"

if [ "$ROOT_PERMS" = "755" ] || [ "$ROOT_PERMS" = "750" ]; then
    echo "  ✓ Права на /root правильные"
else
    echo "  ✗ Права на /root неправильные (нужно 755 или 750)"
    echo "    Выполните: chmod 755 /root"
fi

# Проверка /root/mainstreamfs.ru
APP_PERMS=$(stat -c "%a" "$APP_PATH" 2>/dev/null || stat -f "%OLp" "$APP_PATH" 2>/dev/null)
APP_OWNER=$(stat -c "%U:%G" "$APP_PATH" 2>/dev/null || stat -f "%Su:%Sg" "$APP_PATH" 2>/dev/null)
echo "  $APP_PATH: права=$APP_PERMS, владелец=$APP_OWNER"

if [ "$APP_PERMS" = "755" ] || [ "$APP_PERMS" = "750" ]; then
    echo "  ✓ Права на директорию приложения правильные"
else
    echo "  ✗ Права на директорию приложения неправильные (нужно 755 или 750)"
    echo "    Выполните: chmod 755 $APP_PATH"
fi

# Проверка /root/mainstreamfs.ru/app
APP_DIR_PERMS=$(stat -c "%a" "$APP_PATH/app" 2>/dev/null || stat -f "%OLp" "$APP_PATH/app" 2>/dev/null)
APP_DIR_OWNER=$(stat -c "%U:%G" "$APP_PATH/app" 2>/dev/null || stat -f "%Su:%Sg" "$APP_PATH/app" 2>/dev/null)
echo "  $APP_PATH/app: права=$APP_DIR_PERMS, владелец=$APP_DIR_OWNER"

if [ "$APP_DIR_PERMS" = "755" ] || [ "$APP_DIR_PERMS" = "750" ]; then
    echo "  ✓ Права на app правильные"
else
    echo "  ✗ Права на app неправильные (нужно 755 или 750)"
    echo "    Выполните: chmod 755 $APP_PATH/app"
fi

echo ""
echo "2. Проверка доступа к файлам от имени nginx пользователя..."
echo "───────────────────────────────────────────────────────────────"

# Проверка чтения файлов от имени nginx пользователя
if sudo -u "$NGINX_USER" test -r "$STATIC_PATH/css/main.css" 2>/dev/null; then
    echo "  ✓ $NGINX_USER может читать CSS файл"
else
    echo "  ✗ $NGINX_USER НЕ может читать CSS файл"
    echo "    Проверьте права на родительские директории"
fi

if sudo -u "$NGINX_USER" test -r "$STATIC_PATH/js/main.js" 2>/dev/null; then
    echo "  ✓ $NGINX_USER может читать JS файл"
else
    echo "  ✗ $NGINX_USER НЕ может читать JS файл"
fi

if sudo -u "$NGINX_USER" test -r "$STATIC_PATH/images/logo.png" 2>/dev/null; then
    echo "  ✓ $NGINX_USER может читать логотип"
else
    echo "  ✗ $NGINX_USER НЕ может читать логотип"
fi

echo ""
echo "3. Проверка конфигурации Nginx..."
echo "───────────────────────────────────────────────────────────────"

# Проверка пользователя в конфигурации Nginx
NGINX_CONF="/etc/nginx/nginx.conf"
if [ -f "$NGINX_CONF" ]; then
    NGINX_CONF_USER=$(grep "^user" "$NGINX_CONF" | awk '{print $2}' | sed 's/;//')
    if [ -n "$NGINX_CONF_USER" ]; then
        echo "  Пользователь в nginx.conf: $NGINX_CONF_USER"
    else
        echo "  ⚠ Пользователь не указан в nginx.conf (используется по умолчанию)"
    fi
fi

# Проверка конфигурации сайта
SITE_CONF="/etc/nginx/sites-available/mainstreamfs.ru"
if [ -f "$SITE_CONF" ]; then
    echo "  ✓ Конфигурация сайта найдена"
    STATIC_ALIAS=$(grep -A 2 "location /static/" "$SITE_CONF" | grep "alias" | awk '{print $2}' | sed 's/;$//')
    if [ -n "$STATIC_ALIAS" ]; then
        echo "  Путь к static: $STATIC_ALIAS"
    fi
else
    echo "  ✗ Конфигурация сайта не найдена"
fi

echo ""
echo "4. Рекомендации..."
echo "───────────────────────────────────────────────────────────────"

# Если права неправильные, дать рекомендации
if [ "$ROOT_PERMS" != "755" ] && [ "$ROOT_PERMS" != "750" ]; then
    echo "  → Установите права на /root:"
    echo "    chmod 755 /root"
fi

if [ "$APP_PERMS" != "755" ] && [ "$APP_PERMS" != "750" ]; then
    echo "  → Установите права на директорию приложения:"
    echo "    chmod 755 $APP_PATH"
fi

if [ "$APP_DIR_PERMS" != "755" ] && [ "$APP_DIR_PERMS" != "750" ]; then
    echo "  → Установите права на app:"
    echo "    chmod 755 $APP_PATH/app"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Проверка завершена"
echo "═══════════════════════════════════════════════════════════════"

