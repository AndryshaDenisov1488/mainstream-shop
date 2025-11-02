"""
Base handlers for Telegram bot
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.models import User, Event, Category, Athlete, Order, VideoType, Payment
from app import db
from app.utils.cloudpayments import CloudPaymentsAPI
from app.utils.email import send_user_credentials_email

logger = logging.getLogger(__name__)

class BaseHandler:
    """Base handler class with common methods"""
    
    def __init__(self):
        self.cloudpayments = CloudPaymentsAPI()
    
    async def get_user_from_telegram(self, update: Update) -> User:
        """Get user from database by Telegram ID"""
        user_id = update.effective_user.id
        return User.query.filter_by(telegram_id=str(user_id)).first()
    
    async def send_error_message(self, update: Update, error_msg: str = "Произошла ошибка"):
        """Send error message to user"""
        if update.callback_query:
            await update.callback_query.edit_message_text(f"❌ {error_msg}")
        else:
            await update.message.reply_text(f"❌ {error_msg}")
    
    async def send_success_message(self, update: Update, success_msg: str):
        """Send success message to user"""
        if update.callback_query:
            await update.callback_query.edit_message_text(f"✅ {success_msg}")
        else:
            await update.message.reply_text(f"✅ {success_msg}")
    
    def create_menu_keyboard(self):
        """Create main menu keyboard"""
        keyboard = [
            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
            [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")],
            [InlineKeyboardButton("📞 Поддержка", callback_data="support")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def create_back_keyboard(self, back_action: str):
        """Create keyboard with back button"""
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data=back_action)],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
        ]
        return InlineKeyboardMarkup(keyboard)
