# 🚀 ПОШАГОВАЯ ИНСТРУКЦИЯ РАЗВЕРТЫВАНИЯ НА СЕРВЕР

## 📤 ШАГ 1: ЗАГРУЗИТЬ ИЗМЕНЕНИЯ В GIT

На локальном компьютере (Windows) выполните:

```powershell
# Проверить статус
git status

# Добавить все изменения
git add .

# Закоммитить
git commit -m "Подготовка к production: исправления конфигураций"

# Отправить на GitHub
git push origin main
```

---

## 📥 ШАГ 2: ОБНОВИТЬ КОД НА СЕРВЕРЕ

На сервере (через SSH) выполните:

```bash
cd ~/mainstreamfs.ru

# Обновить код из Git
git pull origin main

# Проверить что файлы обновились
ls -la
ls -la nginx_mainstreamfs.conf
ls -la mainstreamfs.service
```

---

## ⚙️ ШАГ 3: УСТАНОВИТЬ ЗАВИСИМОСТИ

```bash
cd ~/mainstreamfs.ru

# Активировать виртуальное окружение
source venv/bin/activate

# Установить обновленные зависимости (если requirements.txt изменился)
pip install -r requirements.txt

# Проверить что все установлено
pip list | grep -E "(flask|gunicorn|sqlalchemy)"
```

---

## 📁 ШАГ 4: СОЗДАТЬ НЕОБХОДИМЫЕ ДИРЕКТОРИИ

```bash
cd ~/mainstreamfs.ru
mkdir -p logs uploads/xml uploads/chat instance
chmod 755 logs uploads instance
```

---

## 💾 ШАГ 5: СОЗДАТЬ БАЗУ ДАННЫХ SQLITE

```bash
cd ~/mainstreamfs.ru
source venv/bin/activate

# Создать базу данных (SQLite)
SKIP_SCHEDULER=1 python3 create_database_final_v3.py

# Проверить что БД создана
ls -lh instance/app.db
```

---

## 📝 ШАГ 6: СОЗДАТЬ/ОБНОВИТЬ .env ФАЙЛ

```bash
cd ~/mainstreamfs.ru
nano .env
```

Скопируйте и вставьте (ОБЯЗАТЕЛЬНО обновите значения):

```env
FLASK_ENV=production
SECRET_KEY=44a9c7cb6a57b8cc30304047fc4b7762ce9aaf61a643d213c742e7900f8e52af
SESSION_COOKIE_SECURE=True
WTF_CSRF_SSL_STRICT=True

# БАЗА ДАННЫХ - SQLite
DATABASE_URL=sqlite:///instance/app.db

# EMAIL
MAIL_SERVER=smtp.beget.com
MAIL_PORT=465
MAIL_USE_TLS=False
MAIL_USE_SSL=True
MAIL_USERNAME=orders@mainstreamfs.ru
MAIL_PASSWORD=7nmkd4bB!
MAIL_DEFAULT_SENDER=orders@mainstreamfs.ru

# TELEGRAM
TELEGRAM_BOT_TOKEN=8149993826:AAEsqDj2Bm4-vwS78axw33tcaq7swBgH-QI
TELEGRAM_WEBHOOK_URL=https://mainstreamfs.ru/telegram/webhook

# CLOUDPAYMENTS
CLOUDPAYMENTS_PUBLIC_ID=pk_46d0e6977b3b40502eba50d058c5f
CLOUDPAYMENTS_API_SECRET=4b3eaa97656242fa6005369b8646555f
CLOUDPAYMENTS_TEST_MODE=False
CLOUDPAYMENTS_WEBHOOK_URL=https://mainstreamfs.ru/api/cloudpayments/webhook

# СЕРВЕР
PORT=5002
SITE_URL=https://mainstreamfs.ru
TEST_MODE=False

# RATE LIMITING
REDIS_URL=memory://
RATELIMIT_STORAGE_URL=memory://
```

**Сохраните:** `Ctrl+O`, `Enter`, `Ctrl+X`

---

## 🌐 ШАГ 7: НАСТРОИТЬ NGINX

```bash
# Скопировать конфигурацию nginx
sudo cp ~/mainstreamfs.ru/nginx_mainstreamfs.conf /etc/nginx/sites-available/mainstreamfs.ru

# Создать символическую ссылку
sudo ln -sf /etc/nginx/sites-available/mainstreamfs.ru /etc/nginx/sites-enabled/

# Удалить дефолтную конфигурацию (если нужно)
sudo rm -f /etc/nginx/sites-enabled/default

# Проверить конфигурацию nginx
sudo nginx -t

# Если OK - перезагрузить nginx
sudo systemctl reload nginx
```

---

## 🔒 ШАГ 8: НАСТРОИТЬ SSL (Let's Encrypt)

```bash
# Установить certbot (если еще не установлен)
sudo apt update
sudo apt install certbot python3-certbot-nginx -y

# Получить SSL сертификат
sudo certbot --nginx -d mainstreamfs.ru -d www.mainstreamfs.ru

# Следовать инструкциям certbot:
# 1. Введите email
# 2. Примите условия
# 3. Выберите перенаправление HTTP -> HTTPS (2)
```

**После установки SSL, certbot автоматически обновит nginx конфигурацию!**

---

## 🔧 ШАГ 9: НАСТРОИТЬ SYSTEMD SERVICE

```bash
# Скопировать service файл
sudo cp ~/mainstreamfs.ru/mainstreamfs.service /etc/systemd/system/

# Перезагрузить systemd
sudo systemctl daemon-reload

# Включить автозапуск при загрузке системы
sudo systemctl enable mainstreamfs

# Запустить сервис
sudo systemctl start mainstreamfs

# Проверить статус
sudo systemctl status mainstreamfs
```

---

## ✅ ШАГ 10: ПРОВЕРИТЬ РАБОТУ

```bash
# Проверить логи приложения
sudo journalctl -u mainstreamfs -f

# В другом терминале проверить что порт слушается
netstat -tulpn | grep 5002

# Проверить nginx
sudo nginx -t
sudo systemctl status nginx
```

**Откройте в браузере:** `https://mainstreamfs.ru`

---

## 🔄 ПОЛЕЗНЫЕ КОМАНДЫ УПРАВЛЕНИЯ

```bash
# Перезапуск приложения
sudo systemctl restart mainstreamfs

# Остановка
sudo systemctl stop mainstreamfs

# Запуск
sudo systemctl start mainstreamfs

# Просмотр логов
sudo journalctl -u mainstreamfs -f
sudo journalctl -u mainstreamfs --since "1 hour ago"

# Просмотр логов nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## ⚠️ ВАЖНО!

1. **SECRET_KEY** в .env должен быть уникальным и секретным
2. **CLOUDPAYMENTS ключи** - используйте реальные (не тестовые)
3. **Права доступа** - проверьте что nginx может читать `/root/mainstreamfs.ru/app/static/`
4. **SSL обязателен** - без HTTPS платежи не будут работать правильно

---

## 🐛 ЕСЛИ ЧТО-ТО НЕ РАБОТАЕТ

1. Проверьте логи: `sudo journalctl -u mainstreamfs -n 50`
2. Проверьте nginx: `sudo nginx -t`
3. Проверьте порт: `netstat -tulpn | grep 5002`
4. Проверьте права: `ls -la ~/mainstreamfs.ru/app/static/`

