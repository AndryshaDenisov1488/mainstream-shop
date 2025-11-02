"""
Main Telegram Bot for MainStream Shop
Clean implementation with modular handlers
"""

import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from app.telegram_bot.handlers.registration import RegistrationHandler
from app.telegram_bot.handlers.ordering import OrderingHandler
from app.telegram_bot.handlers.orders import OrdersHandler
from app.telegram_bot.handlers.menu import MenuHandler

logger = logging.getLogger(__name__)

# Conversation states
(REGISTRATION, MENU, SELECTING_EVENT, SELECTING_CATEGORY, SELECTING_ATHLETE, 
 SELECTING_VIDEO_TYPE, CONFIRMING_ORDER) = range(7)

class MainStreamBot:
    """MainStream Shop Telegram Bot"""
    
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        
        # Initialize handlers
        self.registration_handler = RegistrationHandler()
        self.ordering_handler = OrderingHandler()
        self.orders_handler = OrdersHandler()
        self.menu_handler = MenuHandler()
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot command handlers"""
        
        # Conversation handler for ordering
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                REGISTRATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.registration_handler.handle_registration)
                ],
                MENU: [
                    CallbackQueryHandler(self.menu_handler.handle_support_callback, pattern='^support$'),
                    CallbackQueryHandler(self.orders_handler.handle_view_orders, pattern='^view_orders$'),
                    CallbackQueryHandler(self.ordering_handler.handle_event_selection, pattern='^start_order$'),
                    CallbackQueryHandler(self.menu_handler.handle_start_command, pattern='^back_to_menu$')
                ],
                SELECTING_EVENT: [
                    CallbackQueryHandler(self.ordering_handler.handle_event_selection, pattern='^(event_|back_to_events)$')
                ],
                SELECTING_CATEGORY: [
                    CallbackQueryHandler(self.ordering_handler.handle_category_selection, pattern='^(category_|back_to_categories)$'),
                    CallbackQueryHandler(self.ordering_handler.handle_event_selection, pattern='^back_to_events$')
                ],
                SELECTING_ATHLETE: [
                    CallbackQueryHandler(self.ordering_handler.handle_athlete_selection, pattern='^(athlete_|back_to_athletes)$'),
                    CallbackQueryHandler(self.ordering_handler.handle_category_selection, pattern='^back_to_categories$')
                ],
                SELECTING_VIDEO_TYPE: [
                    CallbackQueryHandler(self.ordering_handler.handle_video_type_selection, pattern='^(video_|back_to_video_types)$'),
                    CallbackQueryHandler(self.ordering_handler.handle_athlete_selection, pattern='^back_to_athletes$')
                ],
                CONFIRMING_ORDER: [
                    CallbackQueryHandler(self.ordering_handler.handle_order_confirmation, pattern='^(confirm_order|back_to_video_types)$')
                ]
            },
            fallbacks=[CommandHandler('cancel', self.menu_handler.handle_cancel_command)]
        )
        
        self.application.add_handler(conv_handler)
        
        # Regular command handlers
        self.application.add_handler(CommandHandler('menu', self.menu_handler.handle_menu_command))
        self.application.add_handler(CommandHandler('orders', self.orders_handler.handle_view_orders))
        self.application.add_handler(CommandHandler('profile', self.menu_handler.handle_profile_command))
        self.application.add_handler(CommandHandler('help', self.menu_handler.handle_help_command))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        return await self.menu_handler.handle_start_command(update, context)
    
    def run(self):
        """Start the bot"""
        logger.info("Starting MainStream Bot...")
        # This method is deprecated - use application.run_polling() directly
        pass

def create_bot(token: str) -> MainStreamBot:
    """Create and return bot instance"""
    return MainStreamBot(token)
