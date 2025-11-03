# Активация venv и создание базы данных

## Windows (PowerShell)

```powershell
# 1. Активация виртуального окружения
.\venv\Scripts\Activate.ps1

# Если получаете ошибку выполнения скриптов, выполните:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2. Переход в директорию проекта (если еще не там)
cd C:\Users\User\Documents\Разработки\ms

# 3. Создание базы данных
python create_database_final_v3.py

# 4. Проверка создания данных
python -c "from app import create_app, db; from app.models import User, VideoType; app = create_app(); app.app_context().push(); print(f'Пользователей: {User.query.count()}'); print(f'Типов видео: {VideoType.query.count()}')"
```

## Windows (CMD)

```cmd
# 1. Активация виртуального окружения
venv\Scripts\activate.bat

# 2. Создание базы данных
python create_database_final_v3.py
```

## Linux/Mac (включая сервер)

```bash
# 1. Активация виртуального окружения
source venv/bin/activate

# 2. Создание базы данных (на сервере используйте python3)
python3 create_database_final_v3.py

# 3. Проверка создания данных (на сервере)
python3 -c "from app import create_app, db; from app.models import User, VideoType; app = create_app(); app.app_context().push(); print(f'Пользователей: {User.query.count()}'); print(f'Типов видео: {VideoType.query.count()}')"
```

**Примечание для сервера:** На сервере обычно используется `python3` вместо `python`.

## Что создает скрипт:

### Пользователи (пароль для всех: `password123`):
1. **Администратор**: admin@mainstreamfs.ru (роль: ADMIN)
2. **Мама**: mom@mainstreamfs.ru (роль: MOM)
3. **Оператор**: operator@mainstreamfs.ru (роль: OPERATOR)

### Типы видео:
1. **Видео ТВ** - 1490 ₽
2. **Видео спорт** - 990 ₽
3. **Видео ТВ 2 проката** - 2490 ₽
4. **Видео спорт 2 проката** - 1490 ₽

### Системные настройки:
- Название сайта
- Контактный email
- Telegram бот
- WhatsApp номер
- Автоотмена заказов (15 минут)
- Срок действия ссылок (90 дней)

## Важно после создания БД:

1. **Смените пароли** для всех пользователей через админ-панель
2. **Добавьте турниры, категории и спортсменов** через админ-панель
3. **Настройте .env файл** с реальными ключами API

