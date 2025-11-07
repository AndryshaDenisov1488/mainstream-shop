#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Скрипт для проверки статических файлов на сервере
# ═══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════════"
echo "Проверка статических файлов на сервере"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Путь к приложению (измените если нужно)
APP_PATH="/root/mainstreamfs.ru"
STATIC_PATH="$APP_PATH/app/static"

echo "1. Проверка существования директорий..."
echo "───────────────────────────────────────────────────────────────"

# Проверка основной директории
if [ -d "$APP_PATH" ]; then
    echo -e "${GREEN}✓${NC} Директория приложения существует: $APP_PATH"
else
    echo -e "${RED}✗${NC} Директория приложения НЕ существует: $APP_PATH"
    echo "   Проверьте путь к приложению в скрипте!"
    exit 1
fi

# Проверка директории static
if [ -d "$STATIC_PATH" ]; then
    echo -e "${GREEN}✓${NC} Директория static существует: $STATIC_PATH"
else
    echo -e "${RED}✗${NC} Директория static НЕ существует: $STATIC_PATH"
    exit 1
fi

# Проверка поддиректорий
for dir in "css" "js" "images"; do
    if [ -d "$STATIC_PATH/$dir" ]; then
        echo -e "${GREEN}✓${NC} Директория $dir существует"
    else
        echo -e "${RED}✗${NC} Директория $dir НЕ существует"
    fi
done

echo ""
echo "2. Проверка наличия файлов..."
echo "───────────────────────────────────────────────────────────────"

# Проверка CSS
if [ -f "$STATIC_PATH/css/main.css" ]; then
    echo -e "${GREEN}✓${NC} CSS файл существует: css/main.css"
    echo "   Размер: $(du -h "$STATIC_PATH/css/main.css" | cut -f1)"
else
    echo -e "${RED}✗${NC} CSS файл НЕ существует: css/main.css"
fi

# Проверка JS
if [ -f "$STATIC_PATH/js/main.js" ]; then
    echo -e "${GREEN}✓${NC} JS файл существует: js/main.js"
    echo "   Размер: $(du -h "$STATIC_PATH/js/main.js" | cut -f1)"
else
    echo -e "${RED}✗${NC} JS файл НЕ существует: js/main.js"
fi

# Проверка логотипа
if [ -f "$STATIC_PATH/images/logo.png" ]; then
    echo -e "${GREEN}✓${NC} Логотип существует: images/logo.png"
    echo "   Размер: $(du -h "$STATIC_PATH/images/logo.png" | cut -f1)"
    echo "   Тип файла: $(file "$STATIC_PATH/images/logo.png" | cut -d: -f2)"
else
    echo -e "${RED}✗${NC} Логотип НЕ существует: images/logo.png"
fi

echo ""
echo "3. Проверка прав доступа..."
echo "───────────────────────────────────────────────────────────────"

# Проверка прав на директорию static
STATIC_PERMS=$(stat -c "%a" "$STATIC_PATH" 2>/dev/null || stat -f "%OLp" "$STATIC_PATH" 2>/dev/null)
STATIC_OWNER=$(stat -c "%U:%G" "$STATIC_PATH" 2>/dev/null || stat -f "%Su:%Sg" "$STATIC_PATH" 2>/dev/null)

echo "Права на директорию static: $STATIC_PERMS"
echo "Владелец: $STATIC_OWNER"

# Проверка, может ли nginx читать файлы
if [ -r "$STATIC_PATH/css/main.css" ] && [ -r "$STATIC_PATH/js/main.js" ] && [ -r "$STATIC_PATH/images/logo.png" ]; then
    echo -e "${GREEN}✓${NC} Все файлы читаемы"
else
    echo -e "${YELLOW}⚠${NC} Некоторые файлы не читаемы для текущего пользователя"
fi

# Проверка прав на файлы
echo ""
echo "Права на файлы:"
ls -la "$STATIC_PATH/css/" 2>/dev/null | grep -E "\.css$" | head -3
ls -la "$STATIC_PATH/js/" 2>/dev/null | grep -E "\.js$" | head -3
ls -la "$STATIC_PATH/images/" 2>/dev/null | grep -E "\.png$" | head -3

echo ""
echo "4. Проверка конфигурации Nginx..."
echo "───────────────────────────────────────────────────────────────"

NGINX_CONFIG="/etc/nginx/sites-available/mainstreamfs.ru"
if [ -f "$NGINX_CONFIG" ]; then
    echo -e "${GREEN}✓${NC} Конфигурация Nginx найдена"
    
    # Проверка пути к static в nginx
    NGINX_STATIC_PATH=$(grep -A 2 "location /static/" "$NGINX_CONFIG" | grep "alias" | awk '{print $2}' | sed 's/;$//')
    if [ -n "$NGINX_STATIC_PATH" ]; then
        echo "   Путь к static в Nginx: $NGINX_STATIC_PATH"
        
        # Проверка, существует ли этот путь
        if [ -d "$NGINX_STATIC_PATH" ]; then
            echo -e "${GREEN}✓${NC} Путь из Nginx конфигурации существует"
        else
            echo -e "${RED}✗${NC} Путь из Nginx конфигурации НЕ существует!"
            echo "   Ожидаемый путь: $STATIC_PATH"
        fi
    else
        echo -e "${YELLOW}⚠${NC} Не найден блок location /static/ в конфигурации Nginx"
    fi
else
    echo -e "${YELLOW}⚠${NC} Конфигурация Nginx не найдена по пути: $NGINX_CONFIG"
    echo "   Проверьте другие возможные пути:"
    ls -la /etc/nginx/sites-available/ 2>/dev/null | grep -i mainstream
fi

echo ""
echo "5. Проверка доступности через HTTP..."
echo "───────────────────────────────────────────────────────────────"

# Проверка доступности статических файлов через curl
DOMAIN="mainstreamfs.ru"

echo "Проверка доступности статических файлов через HTTPS:"
echo ""

# Проверка CSS
CSS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/static/css/main.css" 2>/dev/null)
if [ "$CSS_STATUS" = "200" ]; then
    echo -e "${GREEN}✓${NC} CSS доступен: https://$DOMAIN/static/css/main.css (HTTP $CSS_STATUS)"
elif [ "$CSS_STATUS" = "404" ]; then
    echo -e "${RED}✗${NC} CSS НЕ найден: https://$DOMAIN/static/css/main.css (HTTP 404)"
elif [ "$CSS_STATUS" = "403" ]; then
    echo -e "${RED}✗${NC} CSS доступ запрещен: https://$DOMAIN/static/css/main.css (HTTP 403)"
else
    echo -e "${YELLOW}⚠${NC} CSS недоступен: https://$DOMAIN/static/css/main.css (HTTP $CSS_STATUS)"
fi

# Проверка JS
JS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/static/js/main.js" 2>/dev/null)
if [ "$JS_STATUS" = "200" ]; then
    echo -e "${GREEN}✓${NC} JS доступен: https://$DOMAIN/static/js/main.js (HTTP $JS_STATUS)"
elif [ "$JS_STATUS" = "404" ]; then
    echo -e "${RED}✗${NC} JS НЕ найден: https://$DOMAIN/static/js/main.js (HTTP 404)"
elif [ "$JS_STATUS" = "403" ]; then
    echo -e "${RED}✗${NC} JS доступ запрещен: https://$DOMAIN/static/js/main.js (HTTP 403)"
else
    echo -e "${YELLOW}⚠${NC} JS недоступен: https://$DOMAIN/static/js/main.js (HTTP $JS_STATUS)"
fi

# Проверка логотипа
LOGO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/static/images/logo.png" 2>/dev/null)
if [ "$LOGO_STATUS" = "200" ]; then
    echo -e "${GREEN}✓${NC} Логотип доступен: https://$DOMAIN/static/images/logo.png (HTTP $LOGO_STATUS)"
elif [ "$LOGO_STATUS" = "404" ]; then
    echo -e "${RED}✗${NC} Логотип НЕ найден: https://$DOMAIN/static/images/logo.png (HTTP 404)"
elif [ "$LOGO_STATUS" = "403" ]; then
    echo -e "${RED}✗${NC} Логотип доступ запрещен: https://$DOMAIN/static/images/logo.png (HTTP 403)"
else
    echo -e "${YELLOW}⚠${NC} Логотип недоступен: https://$DOMAIN/static/images/logo.png (HTTP $LOGO_STATUS)"
fi

echo ""
echo "6. Проверка логов Nginx (последние ошибки)..."
echo "───────────────────────────────────────────────────────────────"

NGINX_ERROR_LOG="/var/log/nginx/error.log"
if [ -f "$NGINX_ERROR_LOG" ] && [ -r "$NGINX_ERROR_LOG" ]; then
    echo "Последние ошибки, связанные со static:"
    grep -i "static" "$NGINX_ERROR_LOG" | tail -5 || echo "   Нет ошибок, связанных со static"
else
    echo -e "${YELLOW}⚠${NC} Лог ошибок Nginx недоступен: $NGINX_ERROR_LOG"
fi

echo ""
echo "7. Рекомендации по исправлению..."
echo "───────────────────────────────────────────────────────────────"

# Проверка и вывод рекомендаций
if [ ! -d "$STATIC_PATH" ]; then
    echo -e "${RED}→${NC} Создайте директорию: mkdir -p $STATIC_PATH/{css,js,images}"
fi

if [ ! -f "$STATIC_PATH/css/main.css" ] || [ ! -f "$STATIC_PATH/js/main.js" ] || [ ! -f "$STATIC_PATH/images/logo.png" ]; then
    echo -e "${RED}→${NC} Скопируйте статические файлы из локальной разработки на сервер"
    echo "   Используйте scp или rsync для копирования директории app/static/"
fi

# Проверка прав
if [ "$STATIC_PERMS" != "755" ] && [ "$STATIC_PERMS" != "755" ]; then
    echo -e "${YELLOW}→${NC} Установите правильные права:"
    echo "   chmod -R 755 $STATIC_PATH"
    echo "   chmod -R 644 $STATIC_PATH/css/*.css"
    echo "   chmod -R 644 $STATIC_PATH/js/*.js"
    echo "   chmod -R 644 $STATIC_PATH/images/*"
fi

# Проверка владельца (nginx обычно работает от www-data или nginx)
NGINX_USER=$(ps aux | grep -E '[n]ginx' | head -1 | awk '{print $1}' || echo "www-data")
echo -e "${YELLOW}→${NC} Убедитесь, что nginx может читать файлы:"
echo "   chown -R $NGINX_USER:$NGINX_USER $STATIC_PATH"
echo "   или"
echo "   chmod -R o+r $STATIC_PATH"

# Проверка конфигурации nginx
if [ -n "$NGINX_STATIC_PATH" ] && [ "$NGINX_STATIC_PATH" != "$STATIC_PATH" ]; then
    echo -e "${RED}→${NC} Путь в конфигурации Nginx не совпадает с реальным путем!"
    echo "   Nginx ожидает: $NGINX_STATIC_PATH"
    echo "   Реальный путь: $STATIC_PATH"
    echo "   Обновите конфигурацию Nginx или создайте симлинк"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Проверка завершена"
echo "═══════════════════════════════════════════════════════════════"

