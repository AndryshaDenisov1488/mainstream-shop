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
                    
                    # Start polling in the event loop (without signal handlers for sub-thread)
                    # We need to manually start polling and keep the loop running
                    async def run_bot():
                        try:
                            await bot_manager.application.initialize()
                            await bot_manager.application.start()
                            # Setup bot commands menu
                            await bot_manager.setup_bot_commands()
                            await bot_manager.application.updater.start_polling(
                                drop_pending_updates=True,
                                allowed_updates=None
                            )
                            logger.info("✅ Telegram bot polling started successfully")
                            
                            # Keep the bot running
                            # The updater will handle polling, we just need to keep the loop alive
                            import asyncio
                            # Create a stop event that will be set when we need to stop
                            stop_event = asyncio.Event()
                            
                            # Wait forever until stop_event is set
                            # This keeps the event loop running while updater handles polling
                            try:
                                await stop_event.wait()
                            except asyncio.CancelledError:
                                logger.info("Bot loop cancelled")
                            
                        except Exception as run_error:
                            logger.error(f"Error in bot run loop: {run_error}", exc_info=True)
                            raise
                        finally:
                            # Cleanup
                            try:
                                # Stop updater if it's running
                                try:
                                    await bot_manager.application.updater.stop()
                                except:
                                    pass
                                await bot_manager.application.stop()
                                await bot_manager.application.shutdown()
                            except Exception as cleanup_error:
                                logger.warning(f"Error during bot cleanup: {cleanup_error}")
                    
                    # Run the bot in the event loop
                    loop.run_until_complete(run_bot())
                    
                except KeyboardInterrupt:
                    logger.info("🛑 Telegram bot stopped by user")
                    # Log bot stop
                    try:
                        from app.models import AuditLog
                        AuditLog.log_telegram_action(
                            telegram_id='system',
                            action='BOT_STOPPED',
                            details={'reason': 'KeyboardInterrupt'}
                        )
                    except:
                        pass
                except Exception as bot_error:
                    logger.error(f"❌ Telegram bot error: {bot_error}", exc_info=True)
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Log bot error
                    try:
                        from app.models import AuditLog
                        AuditLog.log_telegram_action(
                            telegram_id='system',
                            action='BOT_ERROR',
                            details={'error': str(bot_error), 'traceback': traceback.format_exc()}
                        )
                    except:
                        pass
                finally:
                    loop.close()
                    logger.info("🔌 Telegram bot event loop closed")
                    
            except Exception as e:
                logger.error(f"❌ Telegram bot setup error: {e}", exc_info=True)
    
    # Start bot in daemon thread
    bot_thread = threading.Thread(target=bot_worker, daemon=True, name="TelegramBot")
    bot_thread.start()
    
    # Give thread a moment to start and log
    import time
    time.sleep(0.5)  # Small delay to allow initial logging
    
    if bot_thread.is_alive():
        logger.info("🚀 Telegram bot thread started and running")
    else:
        logger.error("❌ Telegram bot thread failed to start or died immediately")
    
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
            logger.info("   Set TELEGRAM_BOT_TOKEN in .env file to enable bot")
            return None
        
        # Skip bot initialization if explicitly disabled
        if app.config.get('SKIP_TELEGRAM_BOT', False):
            logger.info("⚠️ Telegram bot disabled by SKIP_TELEGRAM_BOT flag")
            return None
        
        logger.info(f"🔧 Initializing Telegram bot (token length: {len(bot_token) if bot_token else 0})")
        
        # Start bot in separate thread
        bot_thread = run_bot_in_thread(app)
        
        if bot_thread:
            logger.info("✅ Telegram bot thread created and started")
        else:
            logger.warning("⚠️ Telegram bot thread creation returned None")
        
        return bot_thread
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Telegram bot: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

