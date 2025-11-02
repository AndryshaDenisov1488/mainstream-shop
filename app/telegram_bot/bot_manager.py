"""
Telegram Bot Manager
Handles bot integration with web service database
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
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
    
    def setup_handlers(self):
        """Setup bot command handlers"""
        
        # Conversation handler for ordering
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                REGISTRATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_registration)
                ],
                SELECTING_EVENT: [
                    CallbackQueryHandler(self.handle_event_selection, pattern='^event_')
                ],
                SELECTING_CATEGORY: [
                    CallbackQueryHandler(self.handle_category_selection, pattern='^category_'),
                    CallbackQueryHandler(self.handle_event_selection, pattern='^back_to_events$')
                ],
                SELECTING_ATHLETE: [
                    CallbackQueryHandler(self.handle_athlete_selection, pattern='^athlete_'),
                    CallbackQueryHandler(self.handle_category_selection, pattern='^back_to_categories$')
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
            fallbacks=[CommandHandler('cancel', self.cancel_command)]
        )
        
        self.application.add_handler(conv_handler)
        
        # Regular command handlers
        self.application.add_handler(CommandHandler('menu', self.menu_command))
        self.application.add_handler(CommandHandler('orders', self.orders_command))
        self.application.add_handler(CommandHandler('profile', self.profile_command))
        self.application.add_handler(CommandHandler('help', self.help_command))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        
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
        else:
            # New user or existing user without telegram_id - ask for email first
            await update.message.reply_text(
                "👋 Добро пожаловать в MainStream Shop!\n\n"
                "Для работы с ботом нам нужен ваш email адрес.\n"
                "Введите ваш email:"
            )
            return REGISTRATION
    
    async def handle_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user registration process - starts with email check"""
        text = update.message.text.strip()
        user_data = context.user_data
        
        # First step: check email
        if 'email' not in user_data:
            # Validate email format
            if '@' not in text or '.' not in text.split('@')[-1]:
                await update.message.reply_text(
                    "❌ Некорректный формат email. Пожалуйста, введите правильный email адрес:"
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
                        "📱 Для завершения укажите ваш номер телефона (или отправьте /skip чтобы пропустить):"
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
        
        # Second step: get full name (only for new users)
        elif 'full_name' not in user_data:
            # Skip phone update if /skip command
            if text.lower() == '/skip':
                # This means we're updating existing user's phone (already handled)
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
            
            # Store full name for new user
            user_data['full_name'] = text
            await update.message.reply_text(
                "📱 Введите ваш номер телефона (например: +7 999 123 45 67):"
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
                    "❌ Произошла ошибка при регистрации. Попробуйте еще раз или обратитесь в поддержку."
                )
                context.user_data.clear()
                return ConversationHandler.END
        
        return REGISTRATION
    
    async def handle_event_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle event selection"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "start_order" or query.data == "back_to_events":
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
                        f"{event.name} ({event.start_date.strftime('%d.%m.%Y')})",
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
            event_id = int(query.data.split("_")[1])
            context.user_data['event_id'] = event_id
            
            # Show categories for selected event from database
            event = Event.query.get(event_id)
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
            category_id = int(query.data.split("_")[1])
            context.user_data['category_id'] = category_id
            
            # Show athletes for selected category from database
            category = Category.query.get(category_id)
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
            athlete_id = int(query.data.split("_")[1])
            context.user_data['athlete_id'] = athlete_id
            
            # Show video types from database
            video_types = VideoType.query.filter_by(is_active=True).all()
            
            if not video_types:
                await query.edit_message_text(
                    "❌ Нет доступных типов видео."
                )
                return ConversationHandler.END
            
            athlete = Athlete.query.get(athlete_id)
            
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
    
    async def handle_video_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video type selection"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("video_"):
            video_type_id = int(query.data.split("_")[1])
            context.user_data['video_type_id'] = video_type_id
            
            # Show order confirmation
            event = Event.query.get(context.user_data['event_id'])
            category = Category.query.get(context.user_data['category_id'])
            athlete = Athlete.query.get(context.user_data['athlete_id'])
            video_type = VideoType.query.get(video_type_id)
            
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
                # Get user from database
                user = User.query.filter_by(telegram_id=str(update.effective_user.id)).first()
                if not user:
                    await query.edit_message_text("❌ Пользователь не найден.")
                    return ConversationHandler.END
                
                # Create order in database
                order = Order(
                    order_number=Order.generate_order_number(),
                    generated_order_number=Order.generate_human_order_number(),
                    customer_id=user.id,
                    event_id=context.user_data['event_id'],
                    category_id=context.user_data['category_id'],
                    athlete_id=context.user_data['athlete_id'],
                    video_types=[context.user_data['video_type_id']],
                    total_amount=VideoType.query.get(context.user_data['video_type_id']).price,
                    status='pending_payment',
                    contact_email=user.email,
                    contact_phone=user.phone,
                    contact_first_name=user.full_name.split(' ')[0] if user.full_name else '',
                    contact_last_name=user.full_name.split(' ')[1] if user.full_name and ' ' in user.full_name else ''
                )
                
                db.session.add(order)
                db.session.commit()
                
                # Create payment URL using CloudPayments
                cloudpayments = CloudPaymentsAPI()
                payment_data = cloudpayments.create_payment_widget_data(order, 'card')
                # For Telegram bot, we'll create a simple payment link
                payment_url = f"https://mainstreamfs.ru/payment/process?order_id={order.id}&method=card"
                
                await query.edit_message_text(
                    f"✅ Заказ создан!\n\n"
                    f"📋 Номер заказа: {order.order_number}\n"
                    f"💰 Сумма: {int(order.total_amount)} ₽\n\n"
                    f"Для завершения заказа перейдите по ссылке:\n"
                    f"{payment_url}\n\n"
                    f"После оплаты видео будет готово в течение 3-4 дней."
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
            await update.message.reply_text("У вас пока нет заказов.")
            return
        
        message = "📋 Ваши заказы:\n\n"
        for order in orders:
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'completed': '✅',
                'cancelled': '❌'
            }.get(order.status, '❓')
            
            message += f"{status_emoji} {order.order_number}\n"
            message += f"   {order.event.name}\n"
            message += f"   {order.athlete.name}\n"
            message += f"   {int(order.total_amount)} ₽\n\n"
        
        await update.message.reply_text(message)
    
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
        await update.message.reply_text("❌ Операция отменена.")
        return ConversationHandler.END
    
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
    
    async def send_video_links_to_client(self, order: Order):
        """Send video links to client via Telegram if they are registered"""
        from flask import has_app_context
        
        try:
            # Ensure Flask app context is available
            if not has_app_context():
                logger.error("Flask app context not available for sending Telegram message")
                return False
            
            # Find user by email
            user = User.query.filter_by(email=order.contact_email).first()
            if not user or not user.telegram_id:
                logger.info(f"User {order.contact_email} not found in Telegram or not registered")
                return False
            
            # Prepare message
            message = f"🎉 Ваш заказ #{order.generated_order_number} готов!\n\n"
            message += "📹 Ссылки на видео:\n\n"
            
            if order.video_links:
                for video_type_id, link in order.video_links.items():
                    video_type = VideoType.query.get(video_type_id)
                    if video_type:
                        message += f"• {video_type.name}: {link}\n"
            
            message += f"\n💰 Сумма заказа: {order.total_amount} ₽\n"
            message += f"📅 Дата заказа: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            message += "⚠️ Ссылки действительны 90 дней с момента отправки."
            
            # Send message
            await self.application.bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
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
