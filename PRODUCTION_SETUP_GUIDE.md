# 🚀 ПОЛНОЕ РУКОВОДСТВО ПО РАЗВЕРТЫВАНИЮ НА PRODUCTION

## 📋 ЧТО НУЖНО ИСПРАВИТЬ ПЕРЕД РАЗВЕРТЫВАНИЕМ

### ❌ ПРОБЛЕМЫ КОТОРЫЕ НУЖНО ИСПРАВИТЬ:

1. **start_production.sh** - неправильное имя скрипта БД (уже исправлено ✅)
2. **Пути в конфигурациях** - заменить `/opt/mainstreamshop` на `/root/mainstreamfs.ru`
3. **База данных** - настроить PostgreSQL вместо SQLite
4. **SSL сертификаты** - настроить реальные сертификаты
5. **Nginx конфигурация** - обновить пути к статике

---

## ✅ ЧТО УЖЕ ИСПРАВЛЕНО

- ✅ start_production.sh - имя скрипта БД исправлено
- ✅ nginx_mainstreamfs.conf - создан с правильными путями
- ✅ mainstreamfs.service - создан systemd service файл

---

## 📝 ПОШАГОВАЯ ИНСТРУКЦИЯ РАЗВЕРТЫВАНИЯ

### ШАГ 1: Подготовка на сервере

```bash
cd ~/mainstreamfs.ru

# Активировать виртуальное окружение
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Установить gunicorn если нет
pip install gunicorn
```

### ШАГ 2: Настройка базы данных PostgreSQL

```bash
# Войти в PostgreSQL
sudo -u postgres psql

# В psql выполнить:
CREATE DATABASE mainstream_db;
CREATE USER mainstream_user WITH PASSWORD 'надежный_пароль_здесь';
ALTER ROLE mainstream_user SET client_encoding TO 'utf8';
ALTER ROLE mainstream_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE mainstream_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE mainstream_db TO mainstream_user;
\q
```

### ШАГ 3: Создание .env файла

```bash
cd ~/mainstreamfs.ru
nano .env
```

Вставьте (обновите DATABASE_URL с реальными данными):

```env
FLASK_ENV=production
SECRET_KEY=44a9c7cb6a57b8cc30304047fc4b7762ce9aaf61a643d213c742e7900f8e52af
SESSION_COOKIE_SECURE=True
WTF_CSRF_SSL_STRICT=True

DATABASE_URL=postgresql://mainstream_user:ваш_пароль@localhost/mainstream_db

MAIL_SERVER=smtp.beget.com
MAIL_PORT=465
MAIL_USE_TLS=False
MAIL_USE_SSL=True
MAIL_USERNAME=orders@mainstreamfs.ru
MAIL_PASSWORD=7nmkd4bB!
MAIL_DEFAULT_SENDER=orders@mainstreamfs.ru

TELEGRAM_BOT_TOKEN=8149993826:AAEsqDj2Bm4-vwS78axw33tcaq7swBgH-QI
TELEGRAM_WEBHOOK_URL=https://mainstreamfs.ru/telegram/webhook

CLOUDPAYMENTS_PUBLIC_ID=pk_46d0e6977b3b40502eba50d058c5f
CLOUDPAYMENTS_API_SECRET=4b3eaa97656242fa6005369b8646555f
CLOUDPAYMENTS_TEST_MODE=False
CLOUDPAYMENTS_WEBHOOK_URL=https://mainstreamfs.ru/api/cloudpayments/webhook

PORT=5002
SITE_URL=https://mainstreamfs.ru

TEST_MODE=False

REDIS_URL=memory://
RATELIMIT_STORAGE_URL=memory://
```

### ШАГ 4: Создание директорий

```bash
cd ~/mainstreamfs.ru
mkdir -p logs uploads/xml uploads/chat instance
chmod 755 logs uploads instance
```

### ШАГ 5: Создание базы данных

```bash
cd ~/mainstreamfs.ru
source venv/bin/activate
SKIP_SCHEDULER=1 python3 create_database_final_v3.py
```

### ШАГ 6: Настройка Nginx

```bash
# Скопировать конфигурацию
sudo cp ~/mainstreamfs.ru/nginx_mainstreamfs.conf /etc/nginx/sites-available/mainstreamfs.ru

# Создать симлинк
sudo ln -sf /etc/nginx/sites-available/mainstreamfs.ru /etc/nginx/sites-enabled/

# Удалить дефолтную конфигурацию если нужно
sudo rm -f /etc/nginx/sites-enabled/default

# Проверить конфигурацию
sudo nginx -t

# Перезагрузить nginx
sudo systemctl reload nginx
```

### ШАГ 7: Настройка SSL (Let's Encrypt)

```bash
# Установить certbot
sudo apt install certbot python3-certbot-nginx -y

# Получить сертификат
sudo certbot --nginx -d mainstreamfs.ru -d www.mainstreamfs.ru

# Автоматическое обновление уже настроено certbot
```

### ШАГ 8: Настройка systemd service

```bash
# Скопировать service файл
sudo cp ~/mainstreamfs.ru/mainstreamfs.service /etc/systemd/system/

# Перезагрузить systemd
sudo systemctl daemon-reload

# Включить автозапуск
sudo systemctl enable mainstreamfs

# Запустить сервис
sudo systemctl start mainstreamfs

# Проверить статус
sudo systemctl status mainstreamfs
```

### ШАГ 9: Проверка работы

```bash
# Проверить логи
sudo journalctl -u mainstreamfs -f

# Проверить что порт слушается
netstat -tulpn | grep 5002

# Проверить nginx
sudo nginx -t
```

---

## 🔧 КОМАНДЫ УПРАВЛЕНИЯ

```bash
# Запуск
sudo systemctl start mainstreamfs

# Остановка
sudo systemctl stop mainstreamfs

# Перезапуск
sudo systemctl restart mainstreamfs

# Статус
sudo systemctl status mainstreamfs

# Логи
sudo journalctl -u mainstreamfs -f
sudo journalctl -u mainstreamfs --since "1 hour ago"
```

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **SSL сертификаты** - обязательно настроить перед запуском
2. **База данных** - PostgreSQL обязательна для production
3. **SECRET_KEY** - должен быть уникальным и секретным
4. **Права доступа** - проверьте что nginx может читать статические файлы
5. **Порты** - убедитесь что порт 5002 не занят

