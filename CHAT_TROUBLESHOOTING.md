# Диагностика проблем с чатом

## Как посмотреть логи на сервере

### 1. Логи приложения (основной файл)

```bash
# Посмотреть последние записи о чате
tail -100 /root/mainstreamfs.ru/logs/app.log | grep -i chat

# Смотреть логи в реальном времени
tail -f /root/mainstreamfs.ru/logs/app.log | grep -i chat

# Посмотреть все ошибки, связанные с чатом
grep -i "error\|exception\|failed" /root/mainstreamfs.ru/logs/app.log | grep -i chat | tail -20
```

### 2. Логи Gunicorn (если используется)

```bash
# Ошибки Gunicorn
tail -100 /root/mainstreamfs.ru/logs/gunicorn_error.log | grep -i chat

# В реальном времени
tail -f /root/mainstreamfs.ru/logs/gunicorn_error.log | grep -i chat
```

### 3. Systemd журнал (если приложение запущено через systemd)

```bash
# Последние записи о чате
journalctl -u mainstreamfs.service -n 100 --no-pager | grep -i chat

# В реальном времени
journalctl -u mainstreamfs.service -f | grep -i chat

# Все ошибки
journalctl -u mainstreamfs.service --since "1 hour ago" | grep -i "error\|exception" | grep -i chat
```

### 4. Использование скрипта диагностики

```bash
chmod +x check_chat_logs.sh
./check_chat_logs.sh
```

## Что искать в логах

### Успешная отправка сообщения:
```
INFO: Chat message send attempt: order_id=2, user_id=1, user_role=OPERATOR
INFO: Chat message saved: message_id=1, order_id=2
```

### Ошибки доступа:
```
WARNING: Chat access denied: order_id=2, user_id=1
```

### Ошибки сохранения:
```
ERROR: Failed to save chat message: ...
```

### Общие ошибки:
```
ERROR: Error in send_chat_message: ...
```

## Проверка в браузере (консоль разработчика)

1. Откройте консоль разработчика (F12)
2. Перейдите на вкладку **Console**
3. Попробуйте отправить сообщение
4. Посмотрите на ошибки в консоли

### Типичные ошибки в консоли:

- `Failed to fetch` - проблема с сетью или сервер недоступен
- `HTTP 403` - нет доступа к чату
- `HTTP 500` - ошибка на сервере (смотрите логи)
- `CORS error` - проблема с CORS (маловероятно для одного домена)

## Проверка API напрямую

### Проверка доступности endpoint:

```bash
# На сервере
curl -X POST http://localhost:5002/api/chat/order/2/send \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "message=Тестовое сообщение" \
  -b "session=..." # Нужна сессия авторизованного пользователя
```

### Проверка получения сообщений:

```bash
curl http://localhost:5002/api/chat/order/2/messages \
  -b "session=..." # Нужна сессия
```

## Частые проблемы и решения

### Проблема: "Произошла ошибка при отправке сообщения"

**Что проверить:**
1. Логи приложения (см. выше)
2. Консоль браузера (F12)
3. Статус ответа сервера (Network tab в DevTools)

**Возможные причины:**
- Ошибка в БД (проверьте логи)
- Проблемы с правами доступа к директории uploads/chat/
- Ошибка при отправке уведомлений (не критично, сообщение должно сохраниться)

### Проблема: Сообщения не отображаются

**Что проверить:**
1. Проверьте, сохраняются ли сообщения в БД:
```sql
SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 10;
```

2. Проверьте JavaScript консоль на ошибки

3. Проверьте endpoint получения сообщений:
```bash
curl http://localhost:5002/api/chat/order/2/messages
```

### Проблема: "Нет доступа к чату этого заказа"

**Причины:**
- Оператор не назначен на заказ
- Пользователь не имеет нужной роли (OPERATOR, MOM, ADMIN)

**Решение:**
- Для OPERATOR: назначьте оператора на заказ
- Проверьте роль пользователя в БД

## Проверка базы данных

### Проверить существование чата:

```sql
SELECT * FROM order_chats WHERE order_id = 2;
```

### Проверить сообщения:

```sql
SELECT cm.*, u.email, u.role 
FROM chat_messages cm
JOIN users u ON cm.sender_id = u.id
WHERE cm.chat_id = (SELECT id FROM order_chats WHERE order_id = 2)
ORDER BY cm.created_at DESC;
```

### Проверить назначение оператора:

```sql
SELECT o.id, o.generated_order_number, o.operator_id, u.email as operator_email
FROM orders o
LEFT JOIN users u ON o.operator_id = u.id
WHERE o.id = 2;
```

## После исправления кода

После обновления кода на сервере:

1. Перезапустите приложение:
```bash
sudo systemctl restart mainstreamfs.service
# или
pkill -f gunicorn
# затем запустите снова
```

2. Проверьте логи после перезапуска:
```bash
tail -f /root/mainstreamfs.ru/logs/app.log
```

3. Попробуйте отправить сообщение снова

## Отправка логов для диагностики

Если проблема не решается, соберите следующую информацию:

```bash
# 1. Последние ошибки
tail -50 /root/mainstreamfs.ru/logs/app.log | grep -i "error\|exception\|chat" > chat_errors.log

# 2. Последние записи о чате
tail -100 /root/mainstreamfs.ru/logs/app.log | grep -i chat > chat_logs.log

# 3. Проверка БД
sqlite3 /root/mainstreamfs.ru/instance/app.db "SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 5;" > chat_db_check.txt

# Отправьте эти файлы для анализа
```

