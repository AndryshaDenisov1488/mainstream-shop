# Решение проблем со статическими файлами (CSS, JS, изображения)

## Возможные причины проблем

### 1. **Файлы не загружены на сервер**
   - Статические файлы не были скопированы на сервер при деплое
   - Решение: скопируйте директорию `app/static/` на сервер

### 2. **Неправильный путь в конфигурации Nginx**
   - Путь к статическим файлам в Nginx не совпадает с реальным расположением
   - Решение: проверьте и исправьте путь в `/etc/nginx/sites-available/mainstreamfs.ru`

### 3. **Проблемы с правами доступа**
   - Nginx не может прочитать файлы из-за недостаточных прав
   - Решение: установите правильные права доступа

### 4. **Проблемы с SSL/HTTPS**
   - Смешанный контент (HTTP ресурсы на HTTPS странице)
   - Решение: убедитесь, что все статические файлы загружаются по HTTPS

### 5. **Кэширование браузера**
   - Браузер кэширует старую версию страницы
   - Решение: очистите кэш браузера или используйте Ctrl+F5

## Как проверить на сервере

### Шаг 1: Запустите скрипт диагностики

```bash
# На сервере выполните:
chmod +x check_static_files.sh
./check_static_files.sh
```

Скрипт проверит:
- ✅ Существование директорий и файлов
- ✅ Права доступа
- ✅ Конфигурацию Nginx
- ✅ Доступность файлов через HTTP/HTTPS
- ✅ Логи ошибок

### Шаг 2: Ручная проверка

#### Проверка существования файлов:
```bash
ls -la /root/mainstreamfs.ru/app/static/css/main.css
ls -la /root/mainstreamfs.ru/app/static/js/main.js
ls -la /root/mainstreamfs.ru/app/static/images/logo.png
```

#### Проверка прав доступа:
```bash
ls -la /root/mainstreamfs.ru/app/static/
```

Файлы должны быть читаемы для пользователя nginx (обычно `www-data` или `nginx`).

#### Проверка конфигурации Nginx:
```bash
cat /etc/nginx/sites-available/mainstreamfs.ru | grep -A 5 "location /static/"
```

Должно быть что-то вроде:
```nginx
location /static/ {
    alias /root/mainstreamfs.ru/app/static/;
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

#### Проверка доступности через curl:
```bash
curl -I https://mainstreamfs.ru/static/css/main.css
curl -I https://mainstreamfs.ru/static/js/main.js
curl -I https://mainstreamfs.ru/static/images/logo.png
```

Все должны возвращать `HTTP/2 200`.

#### Проверка логов Nginx:
```bash
tail -50 /var/log/nginx/error.log | grep -i static
```

## Как исправить

### Вариант 1: Использовать скрипт исправления

```bash
chmod +x fix_static_files.sh
sudo ./fix_static_files.sh
```

### Вариант 2: Ручное исправление

#### 1. Скопировать файлы на сервер (с локальной машины):

```bash
# Используя scp
scp -r app/static/ user@mainstreamfs.ru:/root/mainstreamfs.ru/app/

# Или используя rsync
rsync -avz app/static/ user@mainstreamfs.ru:/root/mainstreamfs.ru/app/static/
```

#### 2. Установить права доступа:

```bash
# На сервере
cd /root/mainstreamfs.ru
chmod -R 755 app/static
find app/static -type f -exec chmod 644 {} \;

# Определить пользователя nginx
NGINX_USER=$(ps aux | grep '[n]ginx' | head -1 | awk '{print $1}')

# Установить владельца
sudo chown -R $NGINX_USER:$NGINX_USER app/static
```

#### 3. Проверить и обновить конфигурацию Nginx:

```bash
# Открыть конфигурацию
sudo nano /etc/nginx/sites-available/mainstreamfs.ru

# Убедиться, что блок location /static/ выглядит так:
location /static/ {
    alias /root/mainstreamfs.ru/app/static/;
    expires 1y;
    add_header Cache-Control "public, immutable";
    access_log off;
}
```

#### 4. Проверить и перезагрузить Nginx:

```bash
# Проверить конфигурацию
sudo nginx -t

# Если всё ОК, перезагрузить
sudo systemctl reload nginx
```

## Проверка в браузере

### 1. Откройте консоль разработчика (F12)

### 2. Проверьте вкладку Network (Сеть)

- Найдите запросы к `/static/css/main.css`, `/static/js/main.js`, `/static/images/logo.png`
- Проверьте статус ответа (должен быть 200)
- Если статус 404 или 403 - проблема на сервере
- Если статус 200, но файл не применяется - проблема с кэшем

### 3. Проверьте вкладку Console (Консоль)

- Ищите ошибки типа "Failed to load resource" или "Mixed Content"
- Ошибки Mixed Content означают, что HTTP ресурсы загружаются на HTTPS странице

### 4. Проверьте вкладку Elements (Элементы)

- Найдите тег `<link>` для CSS и проверьте, что путь правильный
- Найдите тег `<img>` для логотипа и проверьте путь

## Частые проблемы и решения

### Проблема: Файлы возвращают 404

**Причины:**
- Файлы не существуют на сервере
- Неправильный путь в Nginx конфигурации
- Nginx не перезагружен после изменения конфигурации

**Решение:**
1. Проверьте существование файлов: `ls -la /root/mainstreamfs.ru/app/static/css/main.css`
2. Проверьте путь в Nginx: `grep -A 2 "location /static/" /etc/nginx/sites-available/mainstreamfs.ru`
3. Перезагрузите Nginx: `sudo systemctl reload nginx`

### Проблема: Файлы возвращают 403 (Forbidden)

**Причины:**
- Недостаточные права доступа
- Nginx не может прочитать файлы

**Решение:**
```bash
sudo chmod -R 755 /root/mainstreamfs.ru/app/static
sudo chown -R www-data:www-data /root/mainstreamfs.ru/app/static
```

### Проблема: Стили не применяются, но файл загружается

**Причины:**
- Кэш браузера
- Неправильный MIME-тип
- Ошибки в CSS файле

**Решение:**
1. Очистите кэш браузера (Ctrl+F5 или Ctrl+Shift+R)
2. Проверьте MIME-тип: `curl -I https://mainstreamfs.ru/static/css/main.css | grep Content-Type`
3. Проверьте синтаксис CSS файла

### Проблема: Mixed Content (смешанный контент)

**Причины:**
- Статические файлы загружаются по HTTP вместо HTTPS

**Решение:**
- Убедитесь, что в шаблонах используется `url_for('static', ...)` (это автоматически использует правильный протокол)
- Проверьте, что Nginx правильно обрабатывает HTTPS

## Быстрая проверка

Выполните на сервере одну команду для быстрой проверки:

```bash
echo "=== Проверка файлов ===" && \
ls -lh /root/mainstreamfs.ru/app/static/css/main.css && \
ls -lh /root/mainstreamfs.ru/app/static/js/main.js && \
ls -lh /root/mainstreamfs.ru/app/static/images/logo.png && \
echo "" && \
echo "=== Проверка прав ===" && \
ls -ld /root/mainstreamfs.ru/app/static && \
echo "" && \
echo "=== Проверка Nginx ===" && \
grep -A 2 "location /static/" /etc/nginx/sites-available/mainstreamfs.ru && \
echo "" && \
echo "=== Проверка доступности ===" && \
curl -I https://mainstreamfs.ru/static/css/main.css 2>&1 | head -1
```

## Контакты для помощи

Если проблема не решается:
1. Запустите `check_static_files.sh` и сохраните вывод
2. Проверьте логи: `tail -100 /var/log/nginx/error.log`
3. Проверьте логи приложения: `tail -100 /root/mainstreamfs.ru/logs/app.log`

