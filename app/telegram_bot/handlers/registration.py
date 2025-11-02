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
        """Handle user registration process - starts with email check"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        text = update.message.text.strip()
        user_data = context.user_data
        
        # First step: check email
        if 'email' not in user_data:
            # Validate email format
            if '@' not in text or '.' not in text.split('@')[-1]:
                await update.message.reply_text(
                    "❌ Некорректный формат email. Пожалуйста, введите правильный email адрес:"
                )
                return 'REGISTRATION'
            
            email = text.lower()
            user_data['email'] = email
            
            # Check if user with this email already exists
            existing_user = User.query.filter_by(email=email).first()
            
            if existing_user:
                # User exists - link telegram_id and welcome
                if existing_user.telegram_id and existing_user.telegram_id != str(update.effective_user.id):
                    await self.send_error_message(
                        update,
                        "❌ Этот email уже привязан к другому Telegram аккаунту.\n"
                        "Обратитесь в поддержку для решения проблемы."
                    )
                    context.user_data.clear()
                    return 'MENU'
                
                # Update existing user with telegram_id
                existing_user.telegram_id = str(update.effective_user.id)
                
                # Update phone if needed (optional)
                if not existing_user.phone:
                    await update.message.reply_text(
                        f"✅ Добро пожаловать обратно, {existing_user.full_name}!\n\n"
                        "Ваш аккаунт связан с Telegram.\n\n"
                        "📱 Для завершения укажите ваш номер телефона (или отправьте /skip чтобы пропустить):"
                    )
                    # Stay in REGISTRATION state to get phone
                    return 'REGISTRATION'
                else:
                    db.session.commit()
                    
                    await update.message.reply_text(
                        f"✅ Добро пожаловать обратно, {existing_user.full_name}!\n\n"
                        "Ваш аккаунт связан с Telegram. Теперь вы можете заказывать видео через бота.",
                        reply_markup=self.create_menu_keyboard()
                    )
                    
                    context.user_data.clear()
                    return 'MENU'
            else:
                # New user - continue registration (ask for full name)
                await update.message.reply_text(
                    "📝 Email не найден в системе. Давайте зарегистрируем вас!\n\n"
                    "Введите ваше ФИО:"
                )
                return 'REGISTRATION'
        
        # Second step: get full name (only for new users) or update phone (for existing users)
        elif 'full_name' not in user_data:
            # Skip phone update if /skip command
            if text.lower() == '/skip':
                existing_user = User.query.filter_by(email=user_data['email']).first()
                if existing_user:
                    existing_user.telegram_id = str(update.effective_user.id)
                    db.session.commit()
                    
                    await update.message.reply_text(
                        f"✅ Добро пожаловать, {existing_user.full_name}!\n\n"
                        "Ваш аккаунт связан с Telegram.",
                        reply_markup=self.create_menu_keyboard()
                    )
                    
                    context.user_data.clear()
                    return 'MENU'
            
            # Store full name for new user
            user_data['full_name'] = text
            await update.message.reply_text(
                "📱 Введите ваш номер телефона (например: +7 999 123 45 67):"
            )
            return 'REGISTRATION'
        
        # Third step: get phone and create user (only for new users)
        elif 'phone' not in user_data:
            # Skip phone update if /skip command
            if text.lower() == '/skip':
                existing_user = User.query.filter_by(email=user_data['email']).first()
                if existing_user:
                    existing_user.telegram_id = str(update.effective_user.id)
                    db.session.commit()
                    
                    await update.message.reply_text(
                        f"✅ Добро пожаловать, {existing_user.full_name}!\n\n"
                        "Ваш аккаунт связан с Telegram.",
                        reply_markup=self.create_menu_keyboard()
                    )
                    
                    context.user_data.clear()
                    return 'MENU'
            
            # Store phone for new user or update existing user's phone
            user_data['phone'] = text
            
            try:
                # Check again if user exists (maybe was created between steps)
                existing_user = User.query.filter_by(email=user_data['email']).first()
                
                if existing_user:
                    # Update existing user
                    existing_user.telegram_id = str(update.effective_user.id)
                    if user_data['phone']:
                        existing_user.phone = user_data['phone']
                    db.session.commit()
                    
                    await update.message.reply_text(
                        f"✅ Добро пожаловать, {existing_user.full_name}!\n\n"
                        "Ваш аккаунт обновлен и связан с Telegram.",
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
                        f"Ваши данные для входа на сайт отправлены на email: {user.email}\n\n"
                        "Теперь вы можете заказывать видео через бота или на сайте.",
                        reply_markup=self.create_menu_keyboard()
                    )
                    
                    return 'MENU'
                    
            except Exception as e:
                logger.error(f"Registration error: {e}", exc_info=True)
                await self.send_error_message(
                    update,
                    "Произошла ошибка при регистрации. Попробуйте еще раз или обратитесь в поддержку."
                )
                context.user_data.clear()
                return 'MENU'
        
        return 'REGISTRATION'
