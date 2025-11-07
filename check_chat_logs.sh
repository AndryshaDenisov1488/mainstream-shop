#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Скрипт для проверки логов чата
# ═══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════════"
echo "Проверка логов чата"
echo "═══════════════════════════════════════════════════════════════"
echo ""

APP_PATH="/root/mainstreamfs.ru"
LOG_FILE="$APP_PATH/logs/app.log"
NGINX_ERROR_LOG="/var/log/nginx/error.log"

echo "1. Последние ошибки приложения (чаты)..."
echo "───────────────────────────────────────────────────────────────"
if [ -f "$LOG_FILE" ]; then
    echo "Последние 20 строк с упоминанием chat:"
    grep -i "chat" "$LOG_FILE" | tail -20 || echo "   Нет записей о чате"
    echo ""
    echo "Последние ошибки:"
    grep -i "error\|exception\|failed" "$LOG_FILE" | grep -i "chat" | tail -10 || echo "   Нет ошибок чата"
else
    echo "⚠ Лог файл не найден: $LOG_FILE"
fi

echo ""
echo "2. Логи Gunicorn (если используется)..."
echo "───────────────────────────────────────────────────────────────"
GUNICORN_ERROR_LOG="$APP_PATH/logs/gunicorn_error.log"
if [ -f "$GUNICORN_ERROR_LOG" ]; then
    echo "Последние ошибки Gunicorn, связанные с чатом:"
    grep -i "chat\|/api/chat" "$GUNICORN_ERROR_LOG" | tail -10 || echo "   Нет ошибок"
else
    echo "⚠ Лог Gunicorn не найден: $GUNICORN_ERROR_LOG"
fi

echo ""
echo "3. Логи Nginx (ошибки доступа)..."
echo "───────────────────────────────────────────────────────────────"
if [ -f "$NGINX_ERROR_LOG" ] && [ -r "$NGINX_ERROR_LOG" ]; then
    echo "Последние ошибки Nginx, связанные с /api/chat:"
    grep -i "/api/chat" "$NGINX_ERROR_LOG" | tail -10 || echo "   Нет ошибок"
else
    echo "⚠ Лог Nginx недоступен: $NGINX_ERROR_LOG"
fi

echo ""
echo "4. Systemd журнал (если приложение запущено через systemd)..."
echo "───────────────────────────────────────────────────────────────"
if systemctl is-active --quiet mainstreamfs.service 2>/dev/null; then
    echo "Последние записи о чате из systemd:"
    journalctl -u mainstreamfs.service -n 50 --no-pager | grep -i "chat" | tail -10 || echo "   Нет записей"
else
    echo "⚠ Сервис mainstreamfs не активен или не найден"
fi

echo ""
echo "5. Проверка доступности API endpoints..."
echo "───────────────────────────────────────────────────────────────"
echo "Проверка endpoint /api/chat/order/2/messages (пример):"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" "http://localhost:5002/api/chat/order/2/messages" 2>/dev/null || echo "   Не удалось подключиться"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Для просмотра логов в реальном времени используйте:"
echo "  tail -f $LOG_FILE | grep -i chat"
echo "═══════════════════════════════════════════════════════════════"

