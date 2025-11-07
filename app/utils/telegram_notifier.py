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
    logger.info(f"Bot manager registered: manager={bot_manager is not None}, loop={loop is not None}, loop_running={loop.is_running() if loop else False}")


def send_video_links_notification(order):
    """
    Synchronous wrapper for sending video links via Telegram
    Can be called from Flask routes
    """
    # ✅ 152-ФЗ: Не логируем email на уровне INFO
    logger.info(f"Attempting to send video links notification for order {order.id}")
    
    if not _bot_manager:
        logger.warning("Telegram bot manager not initialized, skipping notification")
        return False
    
    if not _bot_loop:
        logger.warning("Telegram bot event loop not initialized, skipping notification")
        return False
    
    try:
        # Check if event loop is running
        try:
            loop = asyncio.get_running_loop()
            logger.debug("Found running event loop, using create_task")
            # If we're already in an async context, use create_task
            loop.create_task(_bot_manager.send_video_links_to_client(order))
            logger.info(f"Scheduled video links notification task for order {order.id}")
            return True
        except RuntimeError:
            # No event loop running, schedule in bot's loop
            if _bot_loop.is_running():
                logger.debug("Bot event loop is running, scheduling coroutine")
                asyncio.run_coroutine_threadsafe(
                    _bot_manager.send_video_links_to_client(order),
                    _bot_loop
                )
                logger.info(f"Scheduled video links notification in bot's event loop for order {order.id}")
                return True
            else:
                logger.error("Bot event loop is not running")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {str(e)}", exc_info=True)
        return False


def send_order_created_notification(order):
    """
    Send order created notification to user via Telegram
    Synchronous wrapper for sending order creation notification
    """
    # ✅ 152-ФЗ: Не логируем email на уровне INFO
    logger.info(f"Attempting to send order created notification for order {order.id}")
    
    if not _bot_manager:
        logger.warning("Telegram bot manager not initialized, skipping notification")
        return False
    
    if not _bot_loop:
        logger.warning("Telegram bot event loop not initialized, skipping notification")
        return False
    
    try:
        # Check if event loop is running
        try:
            loop = asyncio.get_running_loop()
            logger.debug("Found running event loop, using create_task for order created notification")
            # If we're already in an async context, use create_task
            loop.create_task(_bot_manager.send_order_created_notification(order))
            logger.info(f"Scheduled order created notification task for order {order.id}")
            return True
        except RuntimeError:
            # No event loop running, schedule in bot's loop
            if _bot_loop.is_running():
                logger.debug("Bot event loop is running, scheduling order created notification coroutine")
                asyncio.run_coroutine_threadsafe(
                    _bot_manager.send_order_created_notification(order),
                    _bot_loop
                )
                logger.info(f"Scheduled order created notification in bot's event loop for order {order.id}")
                return True
            else:
                logger.error(f"Bot event loop is not running (is_running=False)")
                return False
    except Exception as e:
        logger.error(f"Failed to send order created Telegram notification: {str(e)}", exc_info=True)
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
            # ✅ 152-ФЗ: Не логируем email на уровне INFO
            logger.info(f"User for order {order.id} not found in Telegram or not registered")
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

