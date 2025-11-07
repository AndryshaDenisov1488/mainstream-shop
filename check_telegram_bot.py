#!/usr/bin/env python3
"""
Скрипт для проверки работы Telegram бота
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_bot_status():
    """Проверить статус Telegram бота"""
    print("=" * 60)
    print("🔍 Проверка Telegram бота")
    print("=" * 60)
    
    # Check token
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен в .env")
        return False
    
    if token == 'your-telegram-bot-token':
        print("❌ TELEGRAM_BOT_TOKEN имеет значение по умолчанию (не настроен)")
        return False
    
    print(f"✅ TELEGRAM_BOT_TOKEN найден (длина: {len(token)} символов)")
    print(f"   Начало токена: {token[:10]}...")
    
    # Try to import bot
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            from app.telegram_bot.runner import initialize_bot
            
            print("\n🔧 Попытка инициализации бота...")
            bot_thread = initialize_bot(app)
            
            if bot_thread:
                print(f"✅ Бот инициализирован, поток запущен: {bot_thread.is_alive()}")
                print(f"   Имя потока: {bot_thread.name}")
                return True
            else:
                print("❌ Бот не инициализирован (вернул None)")
                return False
                
    except Exception as e:
        print(f"❌ Ошибка при проверке бота: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = check_bot_status()
    sys.exit(0 if success else 1)







