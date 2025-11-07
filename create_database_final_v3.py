#!/usr/bin/env python3
"""
Database creation script for MainStream Shop
Updated to support test mode with nullable customer_id
"""

import os
import sys
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, VideoType, SystemSetting

def create_database(app):
    """Create database tables and populate with initial data"""
    with app.app_context():
        # ✅ Сначала применяем миграции (если есть)
        try:
            from flask_migrate import upgrade
            print("📦 Применение миграций...")
            upgrade()
            print("✅ Миграции применены")
        except Exception as e:
            print(f"⚠️  Миграции не применены (это нормально для первого запуска): {e}")
            # Если миграций нет, создаем таблицы напрямую
            print("📦 Создание таблиц...")
            db.create_all()
            print("✅ Таблицы созданы")
        
        print("\n👥 Создание пользователей...")
        create_users()
        
        print("📹 Создание типов видео...")
        create_video_types()
        
        print("⚙️  Создание системных настроек...")
        create_system_settings()
        
        print("\n✅ База данных успешно создана!")
        print_stats()
        
        print("\n📝 Примечание: Индексы созданы автоматически через db.create_all()")
        print("   Все индексы определены в моделях через index=True")

def create_users():
    """Create initial users"""
    users_data = [
        {
            'email': 'admin@mainstreamfs.ru',
            'full_name': 'Администратор',
            'role': 'ADMIN',
            'is_active': True
        },
        {
            'email': 'operator@mainstreamfs.ru',
            'full_name': 'Оператор',
            'role': 'OPERATOR',
            'is_active': True
        },
        {
            'email': 'mom@mainstreamfs.ru',
            'full_name': 'Мама Елена',
            'role': 'MOM',
            'is_active': True
        }
    ]
    
    for user_data in users_data:
        # Check if user already exists
        existing_user = User.query.filter_by(email=user_data['email']).first()
        if not existing_user:
            user = User(**user_data)
            user.set_password('password123')  # Default password
            db.session.add(user)
    
    db.session.commit()

def create_video_types():
    """Create video types"""
    video_types_data = [
        {'name': 'Видео ТВ', 'description': 'ТВ версия выступления', 'price': 1490.00},
        {'name': 'Видео спорт', 'description': 'Спортивная версия выступления', 'price': 990.00},
        {'name': 'Видео ТВ 2 проката', 'description': 'ТВ версия для 2 прокатов', 'price': 2490.00},
        {'name': 'Видео спорт 2 проката', 'description': 'Спортивная версия для 2 прокатов', 'price': 1490.00}
    ]
    
    for vt_data in video_types_data:
        # Check if video type already exists
        existing_vt = VideoType.query.filter_by(name=vt_data['name']).first()
        if not existing_vt:
            video_type = VideoType(**vt_data)
            db.session.add(video_type)
    
    db.session.commit()

def create_system_settings():
    """Create system settings"""
    settings_data = [
        {'key': 'site_name', 'value': 'MainStream Shop', 'description': 'Название сайта'},
        {'key': 'site_description', 'value': 'Профессиональные видео с турниров по фигурному катанию', 'description': 'Описание сайта'},
        {'key': 'contact_email', 'value': 'support@mainstreamfs.ru', 'description': 'Контактный email'},
        {'key': 'telegram_bot_username', 'value': '@mainstreamshopbot', 'description': 'Имя пользователя Telegram бота'},
        {'key': 'whatsapp_number', 'value': '+7 (999) 123-45-67', 'description': 'Номер WhatsApp'},
        {'key': 'auto_cancel_minutes', 'value': '15', 'description': 'Автоматическая отмена неоплаченных заказов (минуты)'},
        {'key': 'video_link_expiry_days', 'value': '90', 'description': 'Дни действия ссылок на видео'},
    ]
    
    for setting_data in settings_data:
        # Check if setting already exists
        existing_setting = SystemSetting.query.filter_by(key=setting_data['key']).first()
        if not existing_setting:
            setting = SystemSetting(**setting_data)
            db.session.add(setting)
    
    db.session.commit()

def print_stats():
    """Print database statistics"""
    print("\n📊 Статистика базы данных:")
    print(f"👥 Пользователи: {User.query.count()}")
    print(f"📹 Типы видео: {VideoType.query.count()}")
    print(f"⚙️  Системные настройки: {SystemSetting.query.count()}")
    print(f"🏆 Турниры: Добавляются вручную")
    print(f"📂 Категории: Добавляются вручную")
    print(f"🏅 Спортсмены: Добавляются вручную")
    print(f"💳 Заказы: 0 (создаются пользователями)")
    print(f"💰 Платежи: 0 (создаются при оформлении заказов)")

if __name__ == '__main__':
    print("🚀 Создание базы данных MainStream Shop...")
    print("=" * 50)
    
    app = create_app()
    
    try:
        create_database(app)
        print("\n🎉 Готово! База данных создана успешно.")
        print("\n📝 Следующие шаги:")
        print("1. ✅ Добавьте турниры, категории и спортсменов через админ-панель")
        print("\n3. ✅ Настройте .env файл:")
        print("   - SECRET_KEY")
        print("   - MAIL_PASSWORD")
        print("   - CLOUDPAYMENTS_API_SECRET")
        print("   - TELEGRAM_BOT_TOKEN")
        print("\n2. ✅ Запустите приложение: python run.py")
        print("\n3. ✅ Следуйте TESTING_GUIDE.md для полного тестирования")
        
    except Exception as e:
        print(f"\n❌ Ошибка при создании базы данных: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
