"""
Telegram Bot Manager
Handles bot integration with web service database
"""

import logging
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TimedOut, NetworkError, TelegramError
from app.models import User, Event, Category, Athlete, Order, VideoType, Payment
from app import db
from app.utils.cloudpayments import CloudPaymentsAPI
from app.utils.email import send_user_credentials_email
import json
from datetime import datetime

logger = logging.getLogger(__name__)

# Conversation states
(REGISTRATION, SELECTING_EVENT, SELECTING_CATEGORY, SELECTING_ATHLETE, 
 SELECTING_VIDEO_TYPE, CONFIRMING_ORDER) = range(6)

class TelegramBotManager:
    """Telegram Bot Manager with full DB integration"""
    
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
        self.setup_bot_commands()
    
    async def send_message_with_retry(self, chat_id, text, parse_mode=None, reply_markup=None, max_retries=3):
        """
        ✅ Send message with retry logic and exponential backoff
        
        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Parse mode (HTML, Markdown)
            reply_markup: Reply markup (keyboard)
            max_retries: Maximum number of retries
            
        Returns:
            True if message sent successfully, False otherwise
        """
        for attempt in range(max_retries):
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                return True
                
            except RetryAfter as e:
                # Rate limit - wait as requested by Telegram
                wait_time = e.retry_after
                logger.warning(f'Rate limit hit for chat {chat_id}, waiting {wait_time} seconds')
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f'Failed to send message after {max_retries} retries (rate limit)')
                    return False
                    
            except TimedOut as e:
                # Timeout - retry with exponential backoff
                wait_time = 2 ** attempt
                logger.warning(f'Timeout sending message to chat {chat_id}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})')
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f'Failed to send message after {max_retries} retries (timeout)')
                    return False
                    
            except NetworkError as e:
                # Network error - retry with exponential backoff
                wait_time = 2 ** attempt
                logger.warning(f'Network error sending message to chat {chat_id}: {str(e)}, retrying in {wait_time}s')
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f'Failed to send message after {max_retries} retries (network error)')
                    return False
                    
            except TelegramError as e:
                # Other Telegram errors
                if 'bot was blocked by the user' in str(e).lower() or 'user is deactivated' in str(e).lower():
                    # ✅ Пользователь заблокировал бота - просто логируем и пропускаем
                    logger.info(f'Bot blocked by user {chat_id} or user deactivated')
                    return False
                elif 'chat not found' in str(e).lower():
                    logger.info(f'Chat {chat_id} not found')
                    return False
                else:
                    logger.error(f'Telegram error sending message to chat {chat_id}: {str(e)}')
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return False
                    
            except Exception as e:
                logger.error(f'Unexpected error sending message to chat {chat_id}: {str(e)}')
                return False
        
        return False
    
    def setup_handlers(self):
        """Setup bot command handlers"""
        
        # Conversation handler for ordering
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', self.start_command),
                CallbackQueryHandler(self.handle_start_order_callback, pattern='^start_order$')
            ],
            states={
                REGISTRATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_registration),
                    # Handle commands that should interrupt registration
                    CommandHandler('cancel', self.cancel_command),
                    CommandHandler('start', self.start_command),
                ],
                SELECTING_EVENT: [
                    CallbackQueryHandler(self.handle_event_selection, pattern='^event_'),
                    CallbackQueryHandler(self.handle_event_selection, pattern='^back_to_events$')
                ],
                SELECTING_CATEGORY: [
                    CallbackQueryHandler(self.handle_category_selection, pattern='^category_'),
                    CallbackQueryHandler(self.handle_event_selection, pattern='^back_to_events$')
                ],
                SELECTING_ATHLETE: [
                    CallbackQueryHandler(self.handle_athlete_selection, pattern='^athlete_'),
                    CallbackQueryHandler(self.handle_category_selection, pattern='^back_to_categories$'),
                    CallbackQueryHandler(self.handle_show_more_athletes, pattern='^show_more_athletes$')
                ],
                SELECTING_VIDEO_TYPE: [
                    CallbackQueryHandler(self.handle_video_type_selection, pattern='^video_'),
                    CallbackQueryHandler(self.handle_athlete_selection, pattern='^back_to_athletes$')
                ],
                CONFIRMING_ORDER: [
                    CallbackQueryHandler(self.handle_order_confirmation, pattern='^confirm_'),
                    CallbackQueryHandler(self.handle_video_type_selection, pattern='^back_to_video_types$')
                ]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_command),
                CommandHandler('start', self.start_command),  # Allow /start to reset conversation
                CommandHandler('menu', self.reset_to_menu),  # Allow /menu to reset conversation
            ]
        )
        
        self.application.add_handler(conv_handler)
        
        # Callback handlers for menu buttons (outside ConversationHandler)
        # These must be added BEFORE regular command handlers to catch callbacks
        # Note: start_order is now handled in ConversationHandler entry_points
        self.application.add_handler(CallbackQueryHandler(
            self.handle_view_orders_callback,
            pattern='^view_orders$'
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.handle_view_profile_callback,
            pattern='^view_profile$'
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.handle_support_callback_menu,
            pattern='^support$'
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.handle_back_to_menu_callback,
            pattern='^back_to_menu$'
        ))
        
        # Regular command handlers
        self.application.add_handler(CommandHandler('menu', self.menu_command))
        self.application.add_handler(CommandHandler('orders', self.orders_command))
        self.application.add_handler(CommandHandler('profile', self.profile_command))
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('contact', self.contact_command))
    
    async def setup_bot_commands(self):
        """Setup bot menu commands"""
        from telegram import BotCommand
        commands = [
            BotCommand("start", "Начать покупку видео"),
            BotCommand("menu", "Главное меню"),
            BotCommand("orders", "Мои заказы"),
            BotCommand("help", "Помощь по использованию"),
            BotCommand("contact", "Связаться с нами"),
        ]
        try:
            await self.application.bot.set_my_commands(commands)
            logger.info("✅ Bot commands menu configured successfully")
        except Exception as e:
            logger.error(f"❌ Error setting bot commands: {e}")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - resets conversation and starts fresh"""
        user_id = update.effective_user.id
        
        # Clear any existing conversation data
        context.user_data.clear()
        
        try:
            # Check if user exists in database by telegram_id
            user = User.query.filter_by(telegram_id=str(user_id)).first()
            
            if user:
                # Existing user - already linked with Telegram
                keyboard = [
                    [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                    [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                    [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")],
                    [InlineKeyboardButton("📞 Поддержка", callback_data="support")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"Добро пожаловать, {user.full_name}!\n\n"
                    "Выберите действие:",
                    reply_markup=reply_markup
                )
                
                # Log action
                from app.models import AuditLog
                AuditLog.log_telegram_action(
                    telegram_id=str(user_id),
                    action='START_COMMAND',
                    details={'user_id': user.id, 'user_email': user.email}
                )
                
                return ConversationHandler.END
            else:
                # New user or existing user without telegram_id - ask for email first
                await update.message.reply_text(
                    "👋 Добро пожаловать в MainStream Shop!\n\n"
                    "Для работы с ботом нам нужен ваш email адрес.\n"
                    "Введите ваш email:"
                )
                
                # Log action
                from app.models import AuditLog
                AuditLog.log_telegram_action(
                    telegram_id=str(user_id),
                    action='START_COMMAND_NEW_USER',
                    details={'username': update.effective_user.username}
                )
                
                return REGISTRATION
        except Exception as e:
            logger.error(f"Error in start_command: {e}", exc_info=True)
            
            # Log error
            from app.models import AuditLog
            AuditLog.log_telegram_action(
                telegram_id=str(user_id),
                action='START_COMMAND_ERROR',
                details={'error': str(e)}
            )
            
            await update.message.reply_text(
                "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз."
            )
            return ConversationHandler.END
    
    async def handle_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user registration process - starts with email check"""
        try:
            # Check if it's a command (shouldn't happen due to filters, but safety check)
            if update.message.text and update.message.text.startswith('/'):
                # Command was sent - let ConversationHandler handle it via fallback
                return REGISTRATION
            
            text = update.message.text.strip() if update.message.text else ""
            
            if not text:
                await update.message.reply_text(
                    "❌ Пожалуйста, введите текст. Для отмены используйте /cancel"
                )
                return REGISTRATION
            
            user_data = context.user_data
            
            # First step: check email
            if 'email' not in user_data:
                # Validate email format
                if '@' not in text or '.' not in text.split('@')[-1]:
                    await update.message.reply_text(
                        "❌ Некорректный формат email. Пожалуйста, введите правильный email адрес:\n"
                        "(Для отмены используйте /cancel)"
                    )
                    return REGISTRATION
                
                email = text.lower()
                user_data['email'] = email
                
                # Check if user with this email already exists
                existing_user = User.query.filter_by(email=email).first()
                
                if existing_user:
                    # User exists - link telegram_id and welcome
                    if existing_user.telegram_id and existing_user.telegram_id != str(update.effective_user.id):
                        await update.message.reply_text(
                            "❌ Этот email уже привязан к другому Telegram аккаунту.\n"
                            "Обратитесь в поддержку для решения проблемы."
                        )
                        context.user_data.clear()
                        return ConversationHandler.END
                    
                    # Update existing user with telegram_id
                    existing_user.telegram_id = str(update.effective_user.id)
                    
                    # Update phone if needed (optional)
                    if not existing_user.phone:
                        await update.message.reply_text(
                            f"✅ Добро пожаловать обратно, {existing_user.full_name}!\n\n"
                            "Ваш аккаунт связан с Telegram.\n\n"
                            "📱 Для завершения укажите ваш номер телефона в любом формате:\n"
                            "• 89060943936\n"
                            "• 79060943936\n"
                            "• +79060943936\n"
                            "• 9060943936\n"
                            "(Или отправьте /skip чтобы пропустить):"
                        )
                        # Stay in REGISTRATION state to get phone
                        return REGISTRATION
                    else:
                        db.session.commit()
                        
                        keyboard = [
                            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                            [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")],
                            [InlineKeyboardButton("📞 Поддержка", callback_data="support")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await update.message.reply_text(
                            f"✅ Добро пожаловать обратно, {existing_user.full_name}!\n\n"
                            "Ваш аккаунт связан с Telegram. Теперь вы можете заказывать видео через бота.",
                            reply_markup=reply_markup
                        )
                        
                        context.user_data.clear()
                        return ConversationHandler.END
                else:
                    # New user - continue registration (ask for full name)
                    await update.message.reply_text(
                        "📝 Email не найден в системе. Давайте зарегистрируем вас!\n\n"
                        "Введите ваше ФИО:"
                    )
                    return REGISTRATION
            
            # Second step: get full name (only for new users) OR phone for existing user
            elif 'full_name' not in user_data:
                # Check if this is existing user updating phone (has email but no full_name in user_data)
                existing_user = User.query.filter_by(email=user_data.get('email')).first()
                if existing_user and not existing_user.phone:
                    # Existing user without phone - treat input as phone number
                    # Skip phone update if /skip command
                    if text.lower() == '/skip':
                        existing_user.telegram_id = str(update.effective_user.id)
                        db.session.commit()
                        
                        keyboard = [
                            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                            [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await update.message.reply_text(
                            f"✅ Добро пожаловать, {existing_user.full_name}!\n\n"
                            "Ваш аккаунт связан с Telegram.",
                            reply_markup=reply_markup
                        )
                        
                        context.user_data.clear()
                        return ConversationHandler.END
                    
                    # Normalize and validate phone number for existing user
                    from app.utils.validators import normalize_phone
                    
                    normalized_phone = normalize_phone(text.strip())
                    
                    if not normalized_phone or (not normalized_phone.startswith('+7') or len(normalized_phone.replace('+', '')) != 11):
                        await update.message.reply_text(
                            "❌ Некорректный формат номера телефона. Пожалуйста, введите номер в формате:\n"
                            "• 89060943936\n"
                            "• 79060943936\n"
                            "• +79060943936\n"
                            "• 9060943936\n"
                            "(Или отправьте /skip чтобы пропустить, /cancel для отмены)"
                        )
                        return REGISTRATION
                    
                    # Update existing user's phone
                    existing_user.phone = normalized_phone
                    existing_user.telegram_id = str(update.effective_user.id)
                    db.session.commit()
                    
                    keyboard = [
                        [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                        [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                        [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")],
                        [InlineKeyboardButton("📞 Поддержка", callback_data="support")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(
                        f"✅ Добро пожаловать обратно, {existing_user.full_name}!\n\n"
                        "Ваш аккаунт обновлен и связан с Telegram. Теперь вы можете заказывать видео через бота.",
                        reply_markup=reply_markup
                    )
                    
                    context.user_data.clear()
                    return ConversationHandler.END
                
                # Skip phone update if /skip command (for new users)
                if text.lower() == '/skip':
                    # This means we're updating existing user's phone (already handled above)
                    existing_user = User.query.filter_by(email=user_data['email']).first()
                    if existing_user:
                        existing_user.telegram_id = str(update.effective_user.id)
                        db.session.commit()
                        
                        keyboard = [
                            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                            [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await update.message.reply_text(
                            f"✅ Добро пожаловать, {existing_user.full_name}!\n\n"
                            "Ваш аккаунт связан с Telegram.",
                            reply_markup=reply_markup
                        )
                        
                        context.user_data.clear()
                        return ConversationHandler.END
                
                # Validate full name (should not be empty and should not be a command)
                if not text or len(text.strip()) < 2:
                    await update.message.reply_text(
                        "❌ ФИО должно содержать хотя бы 2 символа. Пожалуйста, введите ваше ФИО:\n"
                        "(Для отмены используйте /cancel)"
                    )
                    return REGISTRATION
                
                # Validate that it's not a command
                if text.startswith('/'):
                    await update.message.reply_text(
                        "❌ Пожалуйста, введите ваше ФИО текстом, а не команду.\n"
                        "(Для отмены используйте /cancel)"
                    )
                    return REGISTRATION
                
                # Store full name for new user
                user_data['full_name'] = text.strip()
                await update.message.reply_text(
                    "📱 Введите ваш номер телефона (например: +7 999 123 45 67):\n"
                    "(Или отправьте /skip чтобы пропустить, /cancel для отмены)"
                )
                return REGISTRATION
            
            # Third step: get phone and create user (only for new users)
            elif 'phone' not in user_data:
                # Skip phone update if /skip command
                if text.lower() == '/skip':
                    existing_user = User.query.filter_by(email=user_data['email']).first()
                    if existing_user:
                        existing_user.telegram_id = str(update.effective_user.id)
                        db.session.commit()
                        
                        keyboard = [
                            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await update.message.reply_text(
                            f"✅ Добро пожаловать, {existing_user.full_name}!\n\n"
                            "Ваш аккаунт связан с Telegram.",
                            reply_markup=reply_markup
                        )
                        
                        context.user_data.clear()
                        return ConversationHandler.END
                
                # Normalize and validate phone number
                from app.utils.validators import normalize_phone
                
                if not text or len(text.strip()) < 5:
                    await update.message.reply_text(
                        "❌ Номер телефона слишком короткий. Пожалуйста, введите корректный номер:\n"
                        "(Или отправьте /skip чтобы пропустить, /cancel для отмены)"
                    )
                    return REGISTRATION
                
                # Normalize phone number
                normalized_phone = normalize_phone(text.strip())
                
                if not normalized_phone or (not normalized_phone.startswith('+7') or len(normalized_phone.replace('+', '')) != 11):
                    await update.message.reply_text(
                        "❌ Некорректный формат номера телефона. Пожалуйста, введите номер в формате:\n"
                        "• 89060943936\n"
                        "• 79060943936\n"
                        "• +79060943936\n"
                        "• 9060943936\n"
                        "(Или отправьте /skip чтобы пропустить, /cancel для отмены)"
                    )
                    return REGISTRATION
                
                # Store normalized phone for new user or update existing user's phone
                user_data['phone'] = normalized_phone
                
                try:
                    # Check again if user exists (maybe was created between steps)
                    existing_user = User.query.filter_by(email=user_data['email']).first()
                    
                    if existing_user:
                        # Update existing user
                        existing_user.telegram_id = str(update.effective_user.id)
                        if user_data['phone']:
                            existing_user.phone = user_data['phone']
                        db.session.commit()
                        
                        keyboard = [
                            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await update.message.reply_text(
                            f"✅ Добро пожаловать, {existing_user.full_name}!\n\n"
                            "Ваш аккаунт обновлен и связан с Telegram.",
                            reply_markup=reply_markup
                        )
                        
                        context.user_data.clear()
                        return ConversationHandler.END
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
                        
                        keyboard = [
                            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                            [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await update.message.reply_text(
                            "✅ Регистрация завершена!\n\n"
                            f"Ваши данные для входа на сайт отправлены на email: {user.email}\n\n"
                            "Теперь вы можете заказывать видео через бота или на сайте.",
                            reply_markup=reply_markup
                        )
                        
                        return ConversationHandler.END
                        
                except Exception as e:
                    logger.error(f"Registration error: {e}", exc_info=True)
                    await update.message.reply_text(
                        "❌ Произошла ошибка при регистрации. Попробуйте еще раз или используйте /cancel для отмены."
                    )
                    # Don't clear user_data - allow user to continue from where they left off
                    return REGISTRATION
            
            # No matching step - reset or continue
            return REGISTRATION
        
        except Exception as e:
            logger.error(f"Error in handle_registration: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ Произошла ошибка при регистрации. Попробуйте еще раз или используйте /cancel для отмены."
            )
            # Don't clear user_data - allow user to continue from where they left off
            return REGISTRATION
        
        return REGISTRATION
    
    async def handle_event_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle event selection"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "back_to_events":
            # Show events from database
            events = Event.query.filter_by(is_active=True).order_by(Event.start_date.desc()).limit(10).all()
            
            if not events:
                await query.edit_message_text(
                    "❌ В данный момент нет доступных турниров."
                )
                return ConversationHandler.END
            
            keyboard = []
            for event in events:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{event.name} ({event.start_date.strftime('%d.%m.%Y') if event.start_date else 'N/A'})",
                        callback_data=f"event_{event.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🏆 Выберите турнир:",
                reply_markup=reply_markup
            )
            return SELECTING_EVENT
        
        elif query.data.startswith("event_"):
            try:
                event_id = int(query.data.split("_")[1])
            except (ValueError, IndexError):
                await query.edit_message_text("❌ Ошибка: неверный формат данных события.")
                return ConversationHandler.END
            
            # Validate event exists
            event = Event.query.get(event_id)
            if not event:
                await query.edit_message_text("❌ Турнир не найден.")
                return ConversationHandler.END
            
            if not event.is_active:
                await query.edit_message_text("❌ Этот турнир недоступен.")
                return ConversationHandler.END
            
            context.user_data['event_id'] = event_id
            
            # Show categories for selected event from database
            categories = Category.query.filter_by(event_id=event_id).all()
            
            if not categories:
                await query.edit_message_text(
                    f"❌ В турнире '{event.name}' нет доступных категорий."
                )
                return ConversationHandler.END
            
            keyboard = []
            for category in categories:
                athletes_count = Athlete.query.filter_by(category_id=category.id).count()
                keyboard.append([
                    InlineKeyboardButton(
                        f"{category.name} ({athletes_count} спортсменов)",
                        callback_data=f"category_{category.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_events")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🏆 {event.name}\n\n"
                "📂 Выберите категорию:",
                reply_markup=reply_markup
            )
            return SELECTING_CATEGORY
    
    async def handle_category_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle category selection"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("category_"):
            try:
                category_id = int(query.data.split("_")[1])
            except (ValueError, IndexError):
                await query.edit_message_text("❌ Ошибка: неверный формат данных категории.")
                return ConversationHandler.END
            
            # Validate category exists and belongs to selected event
            category = Category.query.get(category_id)
            if not category:
                await query.edit_message_text("❌ Категория не найдена.")
                return ConversationHandler.END
            
            event_id = context.user_data.get('event_id')
            if event_id and category.event_id != event_id:
                await query.edit_message_text("❌ Категория не принадлежит выбранному турниру.")
                return ConversationHandler.END
            
            context.user_data['category_id'] = category_id
            
            # Show athletes for selected category from database
            athletes = Athlete.query.filter_by(category_id=category_id).all()
            
            if not athletes:
                await query.edit_message_text(
                    f"❌ В категории '{category.name}' нет спортсменов."
                )
                return ConversationHandler.END
            
            keyboard = []
            for athlete in athletes[:20]:  # Limit to 20 athletes
                keyboard.append([
                    InlineKeyboardButton(
                        athlete.name,
                        callback_data=f"athlete_{athlete.id}"
                    )
                ])
            
            if len(athletes) > 20:
                keyboard.append([
                    InlineKeyboardButton(
                        f"Показать еще {len(athletes) - 20} спортсменов",
                        callback_data="show_more_athletes"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_categories")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🏆 {category.event.name}\n"
                f"📂 {category.name}\n\n"
                "👤 Выберите спортсмена:",
                reply_markup=reply_markup
            )
            return SELECTING_ATHLETE
        
        elif query.data == "back_to_categories":
            # Go back to events
            return await self.handle_event_selection(update, context)
    
    async def handle_athlete_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle athlete selection"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("athlete_"):
            try:
                athlete_id = int(query.data.split("_")[1])
            except (ValueError, IndexError):
                await query.edit_message_text("❌ Ошибка: неверный формат данных спортсмена.")
                return ConversationHandler.END
            
            # Validate athlete exists and belongs to selected category
            athlete = Athlete.query.get(athlete_id)
            if not athlete:
                await query.edit_message_text("❌ Спортсмен не найден.")
                return ConversationHandler.END
            
            category_id = context.user_data.get('category_id')
            if category_id and athlete.category_id != category_id:
                await query.edit_message_text("❌ Спортсмен не принадлежит выбранной категории.")
                return ConversationHandler.END
            
            context.user_data['athlete_id'] = athlete_id
            
            # Show video types from database
            video_types = VideoType.query.filter_by(is_active=True).all()
            
            if not video_types:
                await query.edit_message_text(
                    "❌ Нет доступных типов видео."
                )
                return ConversationHandler.END
            
            keyboard = []
            for video_type in video_types:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{video_type.name} - {int(video_type.price)} ₽",
                        callback_data=f"video_{video_type.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_athletes")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🏆 {athlete.category.event.name}\n"
                f"📂 {athlete.category.name}\n"
                f"👤 {athlete.name}\n\n"
                "🎬 Выберите тип видео:",
                reply_markup=reply_markup
            )
            return SELECTING_VIDEO_TYPE
        
        elif query.data == "back_to_athletes":
            # Go back to categories
            return await self.handle_category_selection(update, context)
        
        else:
            # Unknown callback - ignore
            return SELECTING_ATHLETE
    
    async def handle_show_more_athletes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle show more athletes callback"""
        query = update.callback_query
        await query.answer()
        
        # Show all remaining athletes
        category_id = context.user_data.get('category_id')
        if not category_id:
            await query.edit_message_text("❌ Ошибка: не выбрана категория.")
            return ConversationHandler.END
        
        category = Category.query.get(category_id)
        if not category:
            await query.edit_message_text("❌ Ошибка: категория не найдена.")
            return ConversationHandler.END
        
        athletes = Athlete.query.filter_by(category_id=category_id).all()
        
        if not athletes:
            await query.edit_message_text(
                f"❌ В категории '{category.name}' нет спортсменов."
            )
            return ConversationHandler.END
        
        # Show all athletes (not limited to 20)
        keyboard = []
        for athlete in athletes:
            keyboard.append([
                InlineKeyboardButton(
                    athlete.name,
                    callback_data=f"athlete_{athlete.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_categories")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🏆 {category.event.name}\n"
            f"📂 {category.name}\n\n"
            f"👤 Все спортсмены ({len(athletes)}):",
            reply_markup=reply_markup
        )
        return SELECTING_ATHLETE
    
    async def handle_video_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video type selection"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("video_"):
            try:
                video_type_id = int(query.data.split("_")[1])
            except (ValueError, IndexError):
                await query.edit_message_text("❌ Ошибка: неверный формат данных типа видео.")
                return ConversationHandler.END
            
            # Validate video type exists and is active
            video_type = VideoType.query.get(video_type_id)
            if not video_type:
                await query.edit_message_text("❌ Тип видео не найден.")
                return ConversationHandler.END
            
            if not video_type.is_active:
                await query.edit_message_text("❌ Этот тип видео недоступен.")
                return ConversationHandler.END
            
            if not video_type.price or video_type.price <= 0:
                await query.edit_message_text("❌ Ошибка: некорректная цена для типа видео.")
                return ConversationHandler.END
            
            context.user_data['video_type_id'] = video_type_id
            
            # Validate all previous selections
            event_id = context.user_data.get('event_id')
            category_id = context.user_data.get('category_id')
            athlete_id = context.user_data.get('athlete_id')
            
            if not all([event_id, category_id, athlete_id]):
                await query.edit_message_text("❌ Ошибка: неполные данные заказа. Начните заново.")
                return ConversationHandler.END
            
            # Show order confirmation
            event = Event.query.get(event_id)
            category = Category.query.get(category_id)
            athlete = Athlete.query.get(athlete_id)
            
            if not all([event, category, athlete]):
                await query.edit_message_text("❌ Ошибка: данные заказа не найдены. Начните заново.")
                return ConversationHandler.END
            
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить заказ", callback_data="confirm_order")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_video_types")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📋 Подтверждение заказа:\n\n"
                f"🏆 Турнир: {event.name}\n"
                f"📂 Категория: {category.name}\n"
                f"👤 Спортсмен: {athlete.name}\n"
                f"🎬 Видео: {video_type.name}\n"
                f"💰 Стоимость: {int(video_type.price)} ₽\n\n"
                f"Подтвердите заказ для перехода к оплате:",
                reply_markup=reply_markup
            )
            return CONFIRMING_ORDER
        
        elif query.data == "back_to_video_types":
            # Go back to athletes
            return await self.handle_athlete_selection(update, context)
    
    async def handle_order_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle order confirmation"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "confirm_order":
            try:
                # Validate all required data
                event_id = context.user_data.get('event_id')
                category_id = context.user_data.get('category_id')
                athlete_id = context.user_data.get('athlete_id')
                video_type_id = context.user_data.get('video_type_id')
                
                if not all([event_id, category_id, athlete_id, video_type_id]):
                    await query.edit_message_text("❌ Ошибка: неполные данные заказа. Начните заново.")
                    return ConversationHandler.END
                
                # Validate data exists in database
                event = Event.query.get(event_id)
                category = Category.query.get(category_id)
                athlete = Athlete.query.get(athlete_id)
                video_type = VideoType.query.get(video_type_id)
                
                if not all([event, category, athlete, video_type]):
                    await query.edit_message_text("❌ Ошибка: данные заказа не найдены. Начните заново.")
                    return ConversationHandler.END
                
                if not event.is_active:
                    await query.edit_message_text("❌ Этот турнир недоступен.")
                    return ConversationHandler.END
                
                if not video_type.is_active:
                    await query.edit_message_text("❌ Этот тип видео недоступен.")
                    return ConversationHandler.END
                
                if not video_type.price or video_type.price <= 0:
                    await query.edit_message_text("❌ Ошибка: некорректная цена для типа видео.")
                    return ConversationHandler.END
                
                # Get user from database
                user = User.query.filter_by(telegram_id=str(update.effective_user.id)).first()
                if not user:
                    await query.edit_message_text("❌ Пользователь не найден.")
                    return ConversationHandler.END
                
                if not user.email:
                    await query.edit_message_text("❌ У вас не указан email. Обратитесь в поддержку.")
                    return ConversationHandler.END
                
                if not user.phone:
                    await query.edit_message_text("❌ У вас не указан номер телефона. Обратитесь в поддержку.")
                    return ConversationHandler.END
                
                # Create order in database
                order = Order(
                    order_number=Order.generate_order_number(),
                    generated_order_number=Order.generate_human_order_number(),
                    customer_id=user.id,
                    event_id=event_id,
                    category_id=category_id,
                    athlete_id=athlete_id,
                    video_types=[video_type_id],
                    total_amount=video_type.price,
                    status='awaiting_payment',
                    contact_email=user.email,
                    contact_phone=user.phone,
                    contact_first_name=user.full_name.split(' ')[0] if user.full_name else '',
                    contact_last_name=user.full_name.split(' ')[1] if user.full_name and ' ' in user.full_name else ''
                )
                
                db.session.add(order)
                
                # Commit with retry logic for SQLite database locked errors
                import time
                import random
                from sqlalchemy.exc import OperationalError
                
                max_retries = 5
                retry_delay = 0.1
                
                for attempt in range(max_retries):
                    try:
                        db.session.commit()
                        break  # Success
                    except OperationalError as e:
                        if 'database is locked' in str(e).lower() and attempt < max_retries - 1:
                            db.session.rollback()
                            wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                            logger.warning(f'Database locked in bot order creation, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                            time.sleep(wait_time)
                            db.session.add(order)  # Re-add after rollback
                        else:
                            db.session.rollback()
                            logger.error(f'Error creating order in bot after {attempt + 1} attempts: {str(e)}')
                            await query.edit_message_text(
                                "❌ Ошибка создания заказа. База данных временно недоступна. Попробуйте еще раз через несколько секунд."
                            )
                            return ConversationHandler.END
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f'Error creating order in bot: {str(e)}', exc_info=True)
                        await query.edit_message_text(
                            "❌ Произошла ошибка при создании заказа. Попробуйте еще раз."
                        )
                        return ConversationHandler.END
                
                # Log order creation (after successful commit)
                from app.models import AuditLog
                AuditLog.log_telegram_action(
                    telegram_id=str(update.effective_user.id),
                    action='ORDER_CREATED',
                    details={
                        'order_id': order.id,
                        'order_number': order.generated_order_number,
                        'user_id': user.id,
                        'event_id': event_id,
                        'amount': float(video_type.price)
                    }
                )
                
                # Send Telegram notification about order creation (if user has telegram_id)
                try:
                    await self.send_order_created_notification(order)
                except Exception as e:
                    logger.warning(f'Failed to send Telegram notification for order creation: {e}')
                    # Don't fail the whole operation if Telegram notification fails
                
                # Create payment URL - use order payment page
                import os
                site_url = os.environ.get('SITE_URL', 'https://mainstreamfs.ru')
                # Use payment page with order ID
                payment_url = f"{site_url}/payment/{order.id}"
                
                keyboard = [
                    [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
                    [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ Заказ создан!\n\n"
                    f"📋 Номер заказа: {order.generated_order_number}\n"
                    f"💰 Сумма: {int(order.total_amount)} ₽\n\n"
                    f"Нажмите кнопку ниже для оплаты заказа.\n"
                    f"После оплаты видео будет готово в течение 3-4 дней.",
                    reply_markup=reply_markup
                )
                
                # Clear user data
                context.user_data.clear()
                return ConversationHandler.END
                
            except Exception as e:
                logger.error(f"Order creation error: {e}")
                await query.edit_message_text(
                    "❌ Произошла ошибка при создании заказа. Попробуйте еще раз."
                )
                return ConversationHandler.END
        
        elif query.data == "back_to_video_types":
            # Go back to video types
            return await self.handle_video_type_selection(update, context)
    
    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command"""
        user_id = update.effective_user.id
        user = User.query.filter_by(telegram_id=str(user_id)).first()
        
        if not user:
            await update.message.reply_text(
                "Для просмотра заказов необходимо зарегистрироваться. Используйте команду /start"
            )
            return
        
        orders = Order.query.filter_by(customer_id=user.id).order_by(Order.created_at.desc()).limit(10).all()
        
        if not orders:
            await update.message.reply_text(
                "У вас пока нет заказов.\n\nИспользуйте кнопку 'Заказать видео' для создания первого заказа.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ])
            )
            return
        
        message = "📋 Ваши заказы:\n\n"
        for order in orders:
            status_emoji = {
                'awaiting_payment': '⏳',
                'paid': '💰',
                'processing': '🔄',
                'links_sent': '📹',
                'completed': '✅',
                'cancelled_unpaid': '❌',
                'cancelled_manual': '❌',
                'refund_required': '💰',
                'completed_partial_refund': '✅',
                'refunded_full': '❌'
            }.get(order.status, '❓')
            
            status_text = {
                'awaiting_payment': 'Ожидает оплаты',
                'paid': 'Оплачен',
                'processing': 'В обработке',
                'links_sent': 'Ссылки отправлены',
                'completed': 'Выполнен',
                'cancelled_unpaid': 'Отменен',
                'cancelled_manual': 'Отменен',
                'refund_required': 'Требует возврата',
                'completed_partial_refund': 'Выполнен',
                'refunded_full': 'Возвращен'
            }.get(order.status, 'Неизвестно')
            
            message += f"{status_emoji} <b>{order.generated_order_number}</b>\n"
            message += f"   🏆 {order.event.name}\n"
            message += f"   👤 {order.athlete.name}\n"
            message += f"   💰 {int(order.total_amount)} ₽\n"
            message += f"   📊 {status_text}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("📹 Новый заказ", callback_data="start_order")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command"""
        user_id = update.effective_user.id
        user = User.query.filter_by(telegram_id=str(user_id)).first()
        
        if not user:
            await update.message.reply_text(
                "Для использования бота необходимо зарегистрироваться. Используйте команду /start"
            )
            return
        
        keyboard = [
            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
            [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")],
            [InlineKeyboardButton("📞 Поддержка", callback_data="support")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.full_name}!\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel conversation"""
        context.user_data.clear()
        
        # Show menu after cancellation if user is registered
        try:
            user_id = update.effective_user.id
            user = User.query.filter_by(telegram_id=str(user_id)).first()
            
            if user:
                keyboard = [
                    [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                    [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                    [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")],
                    [InlineKeyboardButton("📞 Поддержка", callback_data="support")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "❌ Операция отменена.\n\n"
                    "Выберите действие:",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    "❌ Операция отменена.\n\n"
                    "Используйте /start для начала работы."
                )
        except Exception as e:
            logger.error(f"Error in cancel_command: {e}", exc_info=True)
            await update.message.reply_text("❌ Операция отменена.")
        
        return ConversationHandler.END
    
    async def reset_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reset conversation and show menu"""
        context.user_data.clear()
        return await self.menu_command(update, context)
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /profile command"""
        user_id = update.effective_user.id
        user = User.query.filter_by(telegram_id=str(user_id)).first()
        
        if not user:
            await update.message.reply_text(
                "Для просмотра профиля необходимо зарегистрироваться. Используйте команду /start"
            )
            return
        
        message = f"👤 <b>Ваш профиль:</b>\n\n"
        message += f"📝 <b>Имя:</b> {user.full_name}\n"
        message += f"📧 <b>Email:</b> {user.email}\n"
        message += f"📱 <b>Телефон:</b> {user.phone or 'Не указан'}\n"
        message += f"📅 <b>Дата регистрации:</b> {user.created_at.strftime('%d.%m.%Y')}\n"
        if user.last_login:
            message += f"🕐 <b>Последний вход:</b> {user.last_login.strftime('%d.%m.%Y %H:%M')}\n"
        message += f"\nДля изменения данных обращайтесь в поддержку."
        
        keyboard = [
            [InlineKeyboardButton("📞 Поддержка", callback_data="support")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def contact_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /contact command"""
        message = (
            "📞 <b>Связаться с нами</b>\n\n"
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
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "📞 <b>Поддержка:</b> support@mainstreamfs.ru"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def handle_start_order_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle start_order callback from menu - entry point for ConversationHandler"""
        query = update.callback_query
        await query.answer()
        
        # Clear any previous data
        context.user_data.clear()
        
        # Check if user is authenticated
        user_id = update.effective_user.id
        user = User.query.filter_by(telegram_id=str(user_id)).first()
        
        if not user:
            await query.edit_message_text(
                "❌ Для оформления заказа необходимо зарегистрироваться. Используйте команду /start"
            )
            return ConversationHandler.END
        
        # Show events from database
        events = Event.query.filter_by(is_active=True).order_by(Event.start_date.desc()).limit(10).all()
        
        if not events:
            await query.edit_message_text(
                "❌ В данный момент нет доступных турниров."
            )
            return ConversationHandler.END
        
        keyboard = []
        for event in events:
            keyboard.append([
                InlineKeyboardButton(
                    f"{event.name} ({event.start_date.strftime('%d.%m.%Y') if event.start_date else 'N/A'})",
                    callback_data=f"event_{event.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🏆 Выберите турнир:",
            reply_markup=reply_markup
        )
        return SELECTING_EVENT
    
    async def handle_view_orders_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle view_orders callback button"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user = User.query.filter_by(telegram_id=str(user_id)).first()
        
        if not user:
            await query.edit_message_text(
                "Для просмотра заказов необходимо зарегистрироваться.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")
                ]])
            )
            return
        
        orders = Order.query.filter_by(customer_id=user.id).order_by(Order.created_at.desc()).limit(10).all()
        
        if not orders:
            await query.edit_message_text(
                "У вас пока нет заказов.\n\nИспользуйте кнопку 'Заказать видео' для создания первого заказа.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ])
            )
            return
        
        # Get all video types for display
        all_video_types = VideoType.query.all()
        video_types_dict = {vt.id: vt for vt in all_video_types}
        video_types_dict.update({str(vt.id): vt for vt in all_video_types})
        
        message = "📋 Ваши заказы:\n\n"
        for order in orders:
            status_emoji = {
                'awaiting_payment': '⏳',
                'paid': '💰',
                'processing': '🔄',
                'links_sent': '📹',
                'completed': '✅',
                'cancelled_unpaid': '❌',
                'cancelled_manual': '❌',
                'refund_required': '💰',
                'completed_partial_refund': '✅',
                'refunded_full': '❌'
            }.get(order.status, '❓')
            
            status_text = {
                'awaiting_payment': 'Ожидает оплаты',
                'paid': 'Оплачен',
                'processing': 'В обработке',
                'links_sent': 'Ссылки отправлены',
                'completed': 'Выполнен',
                'cancelled_unpaid': 'Отменен',
                'cancelled_manual': 'Отменен',
                'refund_required': 'Требует возврата',
                'completed_partial_refund': 'Выполнен',
                'refunded_full': 'Возвращен'
            }.get(order.status, 'Неизвестно')
            
            message += f"{status_emoji} <b>{order.generated_order_number}</b>\n"
            message += f"   🏆 {order.event.name}\n"
            message += f"   👤 {order.athlete.name}\n"
            message += f"   💰 {int(order.total_amount)} ₽\n"
            message += f"   📊 {status_text}\n"
            
            # Добавляем ссылки на видео если заказ выполнен и есть ссылки
            completed_statuses = ['links_sent', 'completed', 'completed_partial_refund', 'refunded_partial']
            if order.status in completed_statuses and order.video_links:
                message += f"   📹 Ссылки на видео:\n"
                for video_type_id, link in order.video_links.items():
                    # Try both int and str lookup
                    video_type = None
                    if isinstance(video_type_id, (str, int)):
                        video_type = (video_types_dict.get(video_type_id) or 
                                     video_types_dict.get(str(video_type_id)) or 
                                     video_types_dict.get(int(video_type_id)))
                    if not video_type:
                        video_type = VideoType.query.get(video_type_id)
                    
                    if video_type:
                        message += f"      • {video_type.name}: {link}\n"
                    else:
                        message += f"      • Ссылка: {link}\n"
            
            message += "\n"
        
        keyboard = [
            [InlineKeyboardButton("📹 Новый заказ", callback_data="start_order")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    async def handle_view_profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle view_profile callback button"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user = User.query.filter_by(telegram_id=str(user_id)).first()
        
        if not user:
            await query.edit_message_text(
                "Для просмотра профиля необходимо зарегистрироваться.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")
                ]])
            )
            return
        
        message = f"👤 <b>Ваш профиль:</b>\n\n"
        message += f"📝 <b>Имя:</b> {user.full_name}\n"
        message += f"📧 <b>Email:</b> {user.email}\n"
        message += f"📱 <b>Телефон:</b> {user.phone or 'Не указан'}\n"
        message += f"📅 <b>Дата регистрации:</b> {user.created_at.strftime('%d.%m.%Y')}\n"
        if user.last_login:
            message += f"🕐 <b>Последний вход:</b> {user.last_login.strftime('%d.%m.%Y %H:%M')}\n"
        message += f"\nДля изменения данных обращайтесь в поддержку."
        
        keyboard = [
            [InlineKeyboardButton("📞 Поддержка", callback_data="support")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    async def handle_support_callback_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle support callback button"""
        query = update.callback_query
        await query.answer()
        
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
        
        await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    async def handle_back_to_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back_to_menu callback button"""
        query = update.callback_query
        await query.answer()
        # Показываем меню, адаптируя menu_command для callback
        user_id = update.effective_user.id
        user = User.query.filter_by(telegram_id=str(user_id)).first()
        
        if not user:
            await query.edit_message_text(
                "Для использования бота необходимо зарегистрироваться. Используйте команду /start"
            )
            return
        
        keyboard = [
            [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
            [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
            [InlineKeyboardButton("👤 Профиль", callback_data="view_profile")],
            [InlineKeyboardButton("📞 Поддержка", callback_data="support")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"👋 Добро пожаловать, {user.full_name}!\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    
    async def send_order_created_notification(self, order: Order):
        """Send order created notification to client via Telegram if they are registered"""
        from flask import has_app_context
        
        try:
            # Ensure Flask app context is available
            if not has_app_context():
                logger.error("Flask app context not available for sending Telegram message")
                return False
            
            # Find user by email
            user = User.query.filter_by(email=order.contact_email).first()
            if not user or not user.telegram_id:
                # ✅ 152-ФЗ: Не логируем email на уровне INFO
                logger.info(f"User for order {order.id} not found in Telegram or not registered, skipping Telegram notification")
                return False
            
            # Get video types for display
            video_types_dict = {}
            if order.video_types:
                video_types = VideoType.query.filter(VideoType.id.in_(order.video_types)).all()
                # Store with both int and str keys for compatibility
                video_types_dict = {vt.id: vt for vt in video_types}
                video_types_dict.update({str(vt.id): vt for vt in video_types})
            
            # Prepare message
            message = f"✅ Ваш заказ #{order.generated_order_number} создан!\n\n"
            message += f"🏆 Турнир: {order.event.name}\n"
            message += f"👤 Спортсмен: {order.athlete.name}\n"
            message += f"📂 Категория: {order.category.name}\n\n"
            
            if order.video_types and video_types_dict:
                message += "🎬 Типы видео:\n"
                for video_type_id in order.video_types:
                    # Try both int and str lookup
                    video_type = None
                    if isinstance(video_type_id, (str, int)):
                        video_type = (video_types_dict.get(video_type_id) or 
                                     video_types_dict.get(str(video_type_id)) or 
                                     video_types_dict.get(int(video_type_id)))
                    if video_type:
                        message += f"• {video_type.name}\n"
                message += "\n"
            
            message += f"💰 Сумма к оплате: {int(order.total_amount)} ₽\n"
            message += f"📅 Дата заказа: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            
            if order.status == 'awaiting_payment':
                import os
                site_url = os.environ.get('SITE_URL', 'https://mainstreamfs.ru')
                payment_url = f"{site_url}/payment/{order.id}"
                message += f"💳 Для оплаты перейдите по ссылке:\n{payment_url}\n\n"
            
            message += "📧 Подробности также отправлены на ваш email."
            
            # ✅ Send message with retry logic
            success = await self.send_message_with_retry(
                chat_id=user.telegram_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            if success:
                logger.info(f"Order created notification sent to Telegram user {user.telegram_id} for order {order.id}")
            return success
            
        except Exception as e:
            logger.error(f"Error sending order created notification to Telegram: {str(e)}", exc_info=True)
            return False
    
    async def send_video_links_to_client(self, order: Order):
        """Send video links to client via Telegram if they are registered"""
        from flask import has_app_context
        
        try:
            # Ensure Flask app context is available
            if not has_app_context():
                logger.error("Flask app context not available for sending Telegram message")
                return False
            
            # Find user by email
            # ✅ 152-ФЗ: Не логируем email на уровне INFO
            logger.info(f"[send_video_links] Looking for user for order {order.id}")
            user = User.query.filter_by(email=order.contact_email).first()
            
            if not user:
                logger.info(f"[send_video_links] User for order {order.id} not found in database, skipping Telegram notification")
                return False
            
            if not user.telegram_id:
                logger.info(f"[send_video_links] User (ID: {user.id}) for order {order.id} found but has no telegram_id, skipping Telegram notification")
                return False
            
            logger.info(f"[send_video_links] Found user (ID: {user.id}) for order {order.id} with telegram_id, preparing to send message")
            
            # Get video types for display
            video_types_dict = {}
            if order.video_types:
                video_types = VideoType.query.filter(VideoType.id.in_(order.video_types)).all()
                # Store with both int and str keys for compatibility
                video_types_dict = {vt.id: vt for vt in video_types}
                video_types_dict.update({str(vt.id): vt for vt in video_types})
            
            # Prepare message
            message = f"🎉 Ваш заказ #{order.generated_order_number} готов!\n\n"
            message += "📹 Ссылки на видео:\n\n"
            
            if order.video_links:
                for video_type_id, link in order.video_links.items():
                    # Try both int and str lookup
                    video_type = None
                    if isinstance(video_type_id, (str, int)):
                        video_type = (video_types_dict.get(video_type_id) or 
                                     video_types_dict.get(str(video_type_id)) or 
                                     video_types_dict.get(int(video_type_id)))
                    if not video_type:
                        video_type = VideoType.query.get(video_type_id)
                    if video_type:
                        message += f"• {video_type.name}:\n{link}\n\n"
                    else:
                        message += f"• Ссылка:\n{link}\n\n"
            else:
                message += "Ссылки будут добавлены позже.\n\n"
            
            message += f"💰 Сумма заказа: {int(order.total_amount)} ₽\n"
            message += f"📅 Дата заказа: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            
            # Get video_link_expiry_days from settings
            try:
                from app.utils.settings import get_video_link_expiry_days
                expiry_days = get_video_link_expiry_days()
            except Exception:
                expiry_days = 90  # Fallback to default
            
            message += f"⚠️ Ссылки действительны {expiry_days} дней с момента отправки."
            
            # ✅ Send message with retry logic
            success = await self.send_message_with_retry(
                chat_id=user.telegram_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            if not success:
                logger.error(f"Failed to send video links to Telegram user {user.telegram_id}")
                return False
            
            logger.info(f"Video links sent to Telegram user {user.telegram_id} for order {order.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending video links to Telegram: {str(e)}", exc_info=True)
            return False
    
    def run(self):
        """Start the bot"""
        logger.info("Starting MainStream Bot...")
        self.application.run_polling()

def create_bot_manager(token: str) -> TelegramBotManager:
    """Create and return bot manager instance"""
    return TelegramBotManager(token)
