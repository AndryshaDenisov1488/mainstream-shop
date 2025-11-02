#!/usr/bin/env python3
"""
Local development server for MainStream Shop
"""

import os
import sys
from app import create_app, db
from app.models import User, Event, Category, Athlete, VideoType, Order, Payment, AuditLog, SystemSetting
from app.telegram_bot.bot import create_bot
import threading
import time

def create_test_data():
    """Create test data for local development"""
    print("🔧 Creating test data...")
    
    # Roles are handled as enum in User model, no separate table needed
    
    # Create admin user if doesn't exist
    admin = User.query.filter_by(email='admin@mainstreamfs.ru').first()
    if not admin:
        admin = User(
            email='admin@mainstreamfs.ru',
            full_name='Администратор',
            role='ADMIN',
            phone='+7 999 123 45 67'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        print("✅ Admin user created: admin@mainstreamfs.ru / admin123")
    
    # Create test customer
    customer = User.query.filter_by(email='customer@test.ru').first()
    if not customer:
        customer = User(
            email='customer@test.ru',
            full_name='Тестовый Клиент',
            role='CUSTOMER',
            phone='+7 999 999 99 99'
        )
        customer.set_password('customer123')
        db.session.add(customer)
        print("✅ Test customer created: customer@test.ru / customer123")
    
    # Create test operator
    operator = User.query.filter_by(email='operator@test.ru').first()
    if not operator:
        operator = User(
            email='operator@test.ru',
            full_name='Тестовый Оператор',
            role='OPERATOR',
            phone='+7 999 888 88 88'
        )
        operator.set_password('operator123')
        db.session.add(operator)
        print("✅ Test operator created: operator@test.ru / operator123")
    
    # Create test mom (financial controller)
    mom = User.query.filter_by(email='mom@test.ru').first()
    if not mom:
        mom = User(
            email='mom@test.ru',
            full_name='Финансовый Контролер',
            role='MOM',
            phone='+7 999 777 77 77'
        )
        mom.set_password('mom123')
        db.session.add(mom)
        print("✅ Test mom created: mom@test.ru / mom123")
    
    # Test data creation removed - only admin users are created
    
    # Create video types if they don't exist
    video_types = [
        {'name': 'Спорт версия 1', 'price': 999.00, 'description': 'Обычное видео одного проката, записанное на флешку. FullHD 1920/1080 50p.'},
        {'name': 'ТВ версия 1', 'price': 1499.00, 'description': 'ТВ-видео одного проката: профессиональная графика, замедленные повторы. FullHD 1920/1080 50p.'},
        {'name': 'Спорт версия 2', 'price': 1499.00, 'description': 'Два видео прокатов (КП + ПП), записанные на флешку. FullHD 1920/1080 50p.'},
        {'name': 'ТВ версия 2', 'price': 2499.00, 'description': 'ТВ-видео двух прокатов (КП + ПП): профессиональная графика, повторы. FullHD 1920/1080 50p.'}
    ]
    
    for vt_data in video_types:
        vt = VideoType.query.filter_by(name=vt_data['name']).first()
        if not vt:
            vt = VideoType(
                name=vt_data['name'],
                price=vt_data['price'],
                description=vt_data['description'],
                is_active=True
            )
            db.session.add(vt)
            print(f"✅ Video type created: {vt.name}")
        else:
            print(f"ℹ️ Video type already exists: {vt.name}")
    
    db.session.commit()
    print("✅ Test data creation completed!")

def run_telegram_bot(app):
    """Run Telegram bot in separate thread"""
    import asyncio
    
    with app.app_context():
        try:
            bot_token = app.config.get('TELEGRAM_BOT_TOKEN')
            if bot_token and bot_token != 'your-telegram-bot-token':
                print("🤖 Starting Telegram bot...")
                
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    bot = create_bot(bot_token)
                    # Run the bot in the new event loop
                    loop.run_until_complete(bot.application.run_polling())
                except Exception as bot_error:
                    print(f"❌ Telegram bot error: {bot_error}")
                finally:
                    loop.close()
            else:
                print("⚠️ Telegram bot token not configured, skipping...")
        except Exception as e:
            print(f"❌ Telegram bot setup error: {e}")

def main():
    """Main function"""
    try:
        print("🚀 Starting MainStream Shop Local Development Server")
        print("=" * 60)
        
        # Create app
        print("🔧 Creating Flask application...")
        app = create_app()
        
        with app.app_context():
            # Create database tables
            print("🗄️ Creating database tables...")
            db.create_all()
            
            # Create test data
            create_test_data()
            
            # Log initial system start
            try:
                AuditLog.log_telegram_action('system', 'SYSTEM_START', {
                    'environment': 'development',
                    'timestamp': time.time()
                })
            except Exception as e:
                print(f"⚠️ Warning: Could not log system start: {e}")
        
        # Start Telegram bot in separate thread
        bot_thread = threading.Thread(target=run_telegram_bot, args=(app,), daemon=True)
        bot_thread.start()
        
        # Start Flask app
        print("\n🌐 Starting Flask development server...")
        print("📱 Admin panel: http://localhost:5000/admin")
        print("👤 Customer panel: http://localhost:5000/customer")
        print("🔧 API endpoints: http://localhost:5000/api")
        print("🛡️ Audit system: http://localhost:5000/admin/audit")
        print("\n🔑 Test accounts:")
        print("   Admin: admin@mainstreamfs.ru / admin123")
        print("   Customer: customer@test.ru / customer123")
        print("   Operator: operator@test.ru / operator123")
        print("   Mom: mom@test.ru / mom123")
        print("\n" + "=" * 60)
        
        app.run(
            host='0.0.0.0',
            port=5002,
            debug=True,
            use_reloader=False  # Disable reloader to avoid conflicts with bot thread
        )
        
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure all dependencies are installed: pip install -r requirements.txt")
        print("2. Check if port 5000 is available")
        print("3. Try running: python -m pip install --upgrade pip")
        input("\nPress Enter to exit...")
        sys.exit(1)

if __name__ == '__main__':
    main()
