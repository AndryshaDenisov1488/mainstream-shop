"""
Ordering handlers for Telegram bot
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from flask import current_app, url_for
from datetime import timedelta
from app.models import Event, Category, Athlete, VideoType, Order
from app import db
from app.utils.datetime_utils import moscow_now_naive
from .base import BaseHandler

logger = logging.getLogger(__name__)

class OrderingHandler(BaseHandler):
    """Handle ordering process"""
    
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
                return 'MENU'
            
            keyboard = []
            for event in events:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{event.name} ({event.start_date.strftime('%d.%m.%Y')})",
                        callback_data=f"event_{event.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🏆 Выберите турнир:",
                reply_markup=reply_markup
            )
            return 'SELECTING_EVENT'
        
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
                return 'SELECTING_EVENT'
            
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
            return 'SELECTING_CATEGORY'
    
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
                return 'SELECTING_CATEGORY'
            
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
            return 'SELECTING_ATHLETE'
        
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
                return 'SELECTING_ATHLETE'
            
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
            return 'SELECTING_VIDEO_TYPE'
        
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
            return 'CONFIRMING_ORDER'
        
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
                user = await self.get_user_from_telegram(update)
                if not user:
                    await self.send_error_message(update, "Пользователь не найден.")
                    return 'MENU'
                
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
                    status='awaiting_payment',
                    payment_method='card',
                    payment_expires_at=moscow_now_naive() + timedelta(minutes=15),
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
                            logger.warning(f'Database locked in OrderingHandler, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                            time.sleep(wait_time)
                            db.session.add(order)  # Re-add after rollback
                        else:
                            db.session.rollback()
                            logger.error(f'Error creating order in OrderingHandler after {attempt + 1} attempts: {str(e)}')
                            await query.edit_message_text(
                                "❌ Ошибка создания заказа. База данных временно недоступна. Попробуйте еще раз через несколько секунд."
                            )
                            return 'MENU'
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f'Error creating order in OrderingHandler: {str(e)}', exc_info=True)
                        await query.edit_message_text(
                            "❌ Произошла ошибка при создании заказа. Попробуйте еще раз."
                        )
                        return 'MENU'
                
                # Create payment URL using CloudPayments
                payment_data = self.cloudpayments.create_payment_widget_data(order, 'card')
                # For Telegram bot, we'll create a simple payment link
                try:
                    payment_url = url_for('main.payment_page', order_id=order.id, _external=True)
                except RuntimeError:
                    base_url = current_app.config.get('SITE_URL') or f"https://{current_app.config.get('SERVER_NAME', 'mainstreamfs.ru')}"
                    payment_url = f"{base_url.rstrip('/')}/payment/{order.id}"
                
                keyboard = [
                    [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
                    [InlineKeyboardButton("📋 Мои заказы", callback_data="view_orders")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ Заказ создан!\n\n"
                    f"📋 Номер заказа: {order.order_number}\n"
                    f"💰 Сумма: {int(order.total_amount)} ₽\n\n"
                    f"Нажмите кнопку ниже для оплаты заказа.\n"
                    f"После оплаты видео будет готово в течение 3-4 дней.",
                    reply_markup=reply_markup
                )
                
                # Clear user data
                context.user_data.clear()
                return 'MENU'
                
            except Exception as e:
                logger.error(f"Order creation error: {e}")
                await self.send_error_message(
                    update, 
                    "Произошла ошибка при создании заказа. Попробуйте еще раз."
                )
                return 'MENU'
        
        elif query.data == "back_to_video_types":
            # Go back to video types
            return await self.handle_video_type_selection(update, context)
