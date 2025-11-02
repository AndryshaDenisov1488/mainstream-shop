"""
Telegram Bot Runner
Handles bot startup in separate thread with Flask app context
"""

import logging
import asyncio
import threading
from flask import Flask
from app.telegram_bot.bot_manager import TelegramBotManager, create_bot_manager
from app.utils.telegram_notifier import set_bot_manager

logger = logging.getLogger(__name__)


def run_bot_in_thread(app: Flask):
    """
    Run Telegram bot in separate thread with Flask app context
    """
    def bot_worker():
        """Worker function that runs the bot"""
        with app.app_context():
            try:
                bot_token = app.config.get('TELEGRAM_BOT_TOKEN')
                
                if not bot_token or bot_token == 'your-telegram-bot-token':
                    logger.warning("Telegram bot token not configured, bot will not start")
                    return
                
                logger.info("🤖 Starting Telegram bot...")
                
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Create bot manager
                    bot_manager = create_bot_manager(bot_token)
                    
                    # Register bot manager in notifier utility
                    set_bot_manager(bot_manager, loop)
                    
                    logger.info("✅ Telegram bot initialized successfully")
                    
                    # Run the bot in the event loop
                    loop.run_until_complete(bot_manager.application.run_polling())
                    
                except KeyboardInterrupt:
                    logger.info("🛑 Telegram bot stopped by user")
                except Exception as bot_error:
                    logger.error(f"❌ Telegram bot error: {bot_error}", exc_info=True)
                finally:
                    loop.close()
                    logger.info("🔌 Telegram bot event loop closed")
                    
            except Exception as e:
                logger.error(f"❌ Telegram bot setup error: {e}", exc_info=True)
    
    # Start bot in daemon thread
    bot_thread = threading.Thread(target=bot_worker, daemon=True, name="TelegramBot")
    bot_thread.start()
    logger.info("🚀 Telegram bot thread started")
    
    return bot_thread


def initialize_bot(app: Flask):
    """
    Initialize Telegram bot for the Flask app
    Should be called after app creation
    """
    try:
        bot_token = app.config.get('TELEGRAM_BOT_TOKEN')
        
        if not bot_token or bot_token == 'your-telegram-bot-token':
            logger.info("⚠️ Telegram bot token not configured, bot will not start")
            return None
        
        # Skip bot initialization if explicitly disabled
        if app.config.get('SKIP_TELEGRAM_BOT', False):
            logger.info("⚠️ Telegram bot disabled by SKIP_TELEGRAM_BOT flag")
            return None
        
        # Start bot in separate thread
        bot_thread = run_bot_in_thread(app)
        return bot_thread
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Telegram bot: {e}", exc_info=True)
        return None

