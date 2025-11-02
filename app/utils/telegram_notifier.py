"""
Utility for sending Telegram notifications from Flask app
Provides synchronous wrapper around async Telegram bot
"""

import logging
import asyncio
from flask import current_app
from app.models import User, VideoType

logger = logging.getLogger(__name__)

# Global bot manager instance (will be initialized when bot starts)
_bot_manager = None
_bot_loop = None


def set_bot_manager(bot_manager, loop):
    """Set the global bot manager instance and event loop"""
    global _bot_manager, _bot_loop
    _bot_manager = bot_manager
    _bot_loop = loop


def send_video_links_notification(order):
    """
    Synchronous wrapper for sending video links via Telegram
    Can be called from Flask routes
    """
    if not _bot_manager or not _bot_loop:
        logger.warning("Telegram bot not initialized, skipping notification")
        return False
    
    try:
        # Check if event loop is running
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an async context, use create_task
            loop.create_task(_bot_manager.send_video_links_to_client(order))
            return True
        except RuntimeError:
            # No event loop running, schedule in bot's loop
            if _bot_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    _bot_manager.send_video_links_to_client(order),
                    _bot_loop
                )
                return True
            else:
                logger.error("Bot event loop is not running")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {str(e)}")
        return False


def send_order_notification(order, message_text):
    """
    Send a generic order notification to user via Telegram
    """
    if not _bot_manager or not _bot_loop:
        logger.warning("Telegram bot not initialized, skipping notification")
        return False
    
    try:
        # Find user by email
        user = User.query.filter_by(email=order.contact_email).first()
        if not user or not user.telegram_id:
            logger.info(f"User {order.contact_email} not found in Telegram or not registered")
            return False
        
        async def send_message():
            try:
                from telegram.constants import ParseMode
                await _bot_manager.application.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message_text,
                    parse_mode=ParseMode.HTML
                )
                return True
            except Exception as e:
                logger.error(f"Error sending Telegram message: {str(e)}")
                return False
        
        # Schedule in bot's event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_message())
            return True
        except RuntimeError:
            if _bot_loop and _bot_loop.is_running():
                asyncio.run_coroutine_threadsafe(send_message(), _bot_loop)
                return True
            else:
                logger.error("Bot event loop is not running")
                return False
                
    except Exception as e:
        logger.error(f"Failed to send order notification: {str(e)}")
        return False

