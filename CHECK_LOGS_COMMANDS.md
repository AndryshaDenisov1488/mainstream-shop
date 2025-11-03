# Команды для просмотра логов на сервере

## 1. Общие логи (последние 100 строк)
```bash
sudo journalctl -u mainstreamfs -n 100 --no-pager
```

## 2. Логи с фильтрацией по ошибкам
```bash
sudo journalctl -u mainstreamfs --since "10 minutes ago" --no-pager | grep -i "error\|exception\|traceback\|failed"
```

## 3. Логи scheduler (задачи по расписанию)
```bash
sudo journalctl -u mainstreamfs --since "10 minutes ago" --no-pager | grep -i "scheduler\|cancel_expired\|cleanup"
```

## 4. Логи за определенное время (например, с 01:00)
```bash
sudo journalctl -u mainstreamfs --since "01:00" --no-pager
```

## 5. Логи в реальном времени (live tail)
```bash
sudo journalctl -u mainstreamfs -f
```
(Нажмите Ctrl+C чтобы выйти)

## 6. Проверить статус сервиса
```bash
sudo systemctl status mainstreamfs
```

## 7. Логи с временными метками (более подробно)
```bash
sudo journalctl -u mainstreamfs --since "5 minutes ago" --no-pager -o verbose
```

## 8. Проверить работает ли scheduler
```bash
sudo journalctl -u mainstreamfs --since "1 minute ago" --no-pager | grep -i "scheduler started\|Background scheduler"
```

## 9. Проверить отмену заказов
```bash
sudo journalctl -u mainstreamfs --since "5 minutes ago" --no-pager | grep -i "expired\|cancel"
```

## 10. Все логи с полными строками (без обрезки)
```bash
sudo journalctl -u mainstreamfs --since "10 minutes ago" --no-pager --full
```


