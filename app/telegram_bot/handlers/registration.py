"""
Registration handlers for Telegram bot
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from app.models import User
from app import db
from app.utils.email import send_user_credentials_email
from .base import BaseHandler

logger = logging.getLogger(__name__)

class RegistrationHandler(BaseHandler):
    """Handle user registration process"""
    
    async def handle_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user registration process"""
        text = update.message.text
        user_data = context.user_data
        
        if 'full_name' not in user_data:
            # Store full name
            user_data['full_name'] = text
            await update.message.reply_text(
                "📧 Введите ваш email адрес:"
            )
            return 'REGISTRATION'
        
        elif 'email' not in user_data:
            # Store email
            user_data['email'] = text
            await update.message.reply_text(
                "📱 Введите ваш номер телефона (например: +7 999 123 45 67):"
            )
            return 'REGISTRATION'
        
        elif 'phone' not in user_data:
            # Store phone and create user in database
            user_data['phone'] = text
            
            try:
                # Check if user with this email already exists
                existing_user = User.query.filter_by(email=user_data['email'].lower()).first()
                
                if existing_user:
                    # Update existing user with telegram_id
                    existing_user.telegram_id = str(update.effective_user.id)
                    existing_user.phone = user_data['phone']
                    db.session.commit()
                    
                    await update.message.reply_text(
                        f"✅ Добро пожаловать обратно, {existing_user.full_name}!\n\n"
                        "Ваш аккаунт связан с Telegram. Теперь вы можете заказывать видео через бота.",
                        reply_markup=self.create_menu_keyboard()
                    )
                    
                    context.user_data.clear()
                    return 'MENU'
                else:
                    # Create new user
                    user = User(
                        email=user_data['email'].lower(),
                        full_name=user_data['full_name'],
                        phone=user_data['phone'],
                        role='CUSTOMER',
                        telegram_id=str(update.effective_user.id)
                    )
                    
                    # Generate password
                    password = User.generate_password()
                    user.set_password(password)
                    
                    db.session.add(user)
                    db.session.commit()
                    
                    # Send credentials email
                    send_user_credentials_email(user, password)
                    
                    # Clear user data
                    context.user_data.clear()
                    
                    await update.message.reply_text(
                        "✅ Регистрация завершена!\n\n"
                        f"Ваши данные для входа отправлены на email: {user.email}\n\n"
                        "Теперь вы можете заказывать видео через бота или на сайте.",
                        reply_markup=self.create_menu_keyboard()
                    )
                    
                    return 'MENU'
                    
            except Exception as e:
                logger.error(f"Registration error: {e}")
                await self.send_error_message(
                    update, 
                    "Произошла ошибка при регистрации. Попробуйте еще раз или обратитесь в поддержку."
                )
                return 'MENU'
        
        return 'REGISTRATION'
