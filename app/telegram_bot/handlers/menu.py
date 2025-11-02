"""
Menu handlers for Telegram bot
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .base import BaseHandler

logger = logging.getLogger(__name__)

class MenuHandler(BaseHandler):
    """Handle main menu operations"""
    
    async def handle_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = await self.get_user_from_telegram(update)
        
        if user:
            # Existing user - already linked with Telegram
            await update.message.reply_text(
                f"Добро пожаловать, {user.full_name}!\n\n"
                "Выберите действие:",
                reply_markup=self.create_menu_keyboard()
            )
            return 'MENU'
        else:
            # New user or existing user without telegram_id - ask for email first
            await update.message.reply_text(
                "👋 Добро пожаловать в MainStream Shop!\n\n"
                "Для работы с ботом нам нужен ваш email адрес.\n"
                "Введите ваш email:"
            )
            return 'REGISTRATION'
    
    async def handle_menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command"""
        user = await self.get_user_from_telegram(update)
        
        if not user:
            await self.send_error_message(
                update, 
                "Для использования бота необходимо зарегистрироваться. Используйте команду /start"
            )
            return 'REGISTRATION'
        
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.full_name}!\n\n"
            "Выберите действие:",
            reply_markup=self.create_menu_keyboard()
        )
        return 'MENU'
    
    async def handle_profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /profile command"""
        user = await self.get_user_from_telegram(update)
        
        if not user:
            await self.send_error_message(
                update, 
                "Для просмотра профиля необходимо зарегистрироваться. Используйте команду /start"
            )
            return 'REGISTRATION'
        
        message = f"👤 <b>Ваш профиль:</b>\n\n"
        message += f"📝 <b>Имя:</b> {user.full_name}\n"
        message += f"📧 <b>Email:</b> {user.email}\n"
        message += f"📱 <b>Телефон:</b> {user.phone or 'Не указан'}\n"
        message += f"📅 <b>Дата регистрации:</b> {user.created_at.strftime('%d.%m.%Y')}\n"
        message += f"🤖 <b>Telegram ID:</b> {user.telegram_id}\n\n"
        message += f"Для изменения данных обращайтесь в поддержку."
        
        keyboard = [
            [InlineKeyboardButton("📞 Поддержка", callback_data="support")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message, 
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        
        return 'MENU'
    
    async def handle_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        message = (
            "🆘 <b>Справка по MainStream Shop Bot</b>\n\n"
            "📋 <b>Доступные команды:</b>\n"
            "/start - Начать работу с ботом\n"
            "/menu - Главное меню\n"
            "/orders - Мои заказы\n"
            "/profile - Мой профиль\n"
            "/help - Эта справка\n\n"
            "📹 <b>Как сделать заказ:</b>\n"
            "1. Используйте команду /start или /menu\n"
            "2. Выберите 'Заказать видео'\n"
            "3. Выберите турнир, категорию и спортсмена\n"
            "4. Выберите тип видео\n"
            "5. Подтвердите заказ и оплатите\n\n"
            "⏰ Видео будет готово в течение 3-4 дней.\n\n"
            "📞 <b>Поддержка:</b> @mainstream_support"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message, 
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message, 
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        
        return 'MENU'
    
    async def handle_support_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle support callback"""
        message = (
            "📞 <b>Поддержка MainStream Shop</b>\n\n"
            "🆘 <b>Нужна помощь?</b>\n"
            "Обращайтесь к нам любым удобным способом:\n\n"
            "📧 <b>Email:</b> support@mainstreamfs.ru\n"
            "🌐 <b>Сайт:</b> https://mainstreamfs.ru\n"
            "📱 <b>Telegram:</b> @mainstream_support\n\n"
            "⏰ <b>Время работы:</b>\n"
            "Пн-Пт: 9:00 - 18:00\n"
            "Сб-Вс: 10:00 - 16:00\n\n"
            "💬 Мы отвечаем в течение рабочего дня!"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            message, 
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return 'MENU'
    
    async def handle_cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel conversation"""
        context.user_data.clear()
        await update.message.reply_text("❌ Операция отменена.")
        return 'MENU'
