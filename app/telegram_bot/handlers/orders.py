"""
Orders handlers for Telegram bot
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.models import Order
from .base import BaseHandler

logger = logging.getLogger(__name__)

class OrdersHandler(BaseHandler):
    """Handle orders viewing"""
    
    async def handle_view_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command and view orders callback"""
        user = await self.get_user_from_telegram(update)
        
        if not user:
            await self.send_error_message(
                update, 
                "Для просмотра заказов необходимо зарегистрироваться. Используйте команду /start"
            )
            return 'MENU'
        
        orders = Order.query.filter_by(customer_id=user.id).order_by(Order.created_at.desc()).limit(10).all()
        
        if not orders:
            message = "У вас пока нет заказов.\n\nИспользуйте кнопку 'Заказать видео' для создания первого заказа."
            keyboard = [
                [InlineKeyboardButton("📹 Заказать видео", callback_data="start_order")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message, reply_markup=reply_markup)
            return 'MENU'
        
        message = "📋 Ваши заказы:\n\n"
        for order in orders:
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'completed': '✅',
                'cancelled': '❌'
            }.get(order.status, '❓')
            
            status_text = {
                'pending': 'Ожидает оплаты',
                'processing': 'В обработке',
                'completed': 'Выполнен',
                'cancelled': 'Отменен'
            }.get(order.status, 'Неизвестно')
            
            message += f"{status_emoji} <b>{order.order_number}</b>\n"
            message += f"   🏆 {order.event.name}\n"
            message += f"   👤 {order.athlete.name}\n"
            message += f"   💰 {int(order.total_amount)} ₽\n"
            message += f"   📅 {order.created_at.strftime('%d.%m.%Y')}\n"
            message += f"   📊 {status_text}\n\n"
        
        # Add keyboard
        keyboard = [
            [InlineKeyboardButton("📹 Новый заказ", callback_data="start_order")],
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
    
    async def handle_order_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int):
        """Handle order detail view"""
        user = await self.get_user_from_telegram(update)
        
        if not user:
            await self.send_error_message(update, "Пользователь не найден.")
            return 'MENU'
        
        order = Order.query.filter_by(id=order_id, customer_id=user.id).first()
        
        if not order:
            await self.send_error_message(update, "Заказ не найден.")
            return 'MENU'
        
        status_text = {
            'pending': '⏳ Ожидает оплаты',
            'processing': '🔄 В обработке',
            'completed': '✅ Выполнен',
            'cancelled': '❌ Отменен'
        }.get(order.status, '❓ Неизвестно')
        
        message = f"📋 <b>Заказ {order.order_number}</b>\n\n"
        message += f"🏆 <b>Турнир:</b> {order.event.name}\n"
        message += f"📂 <b>Категория:</b> {order.category.name}\n"
        message += f"👤 <b>Спортсмен:</b> {order.athlete.name}\n"
        message += f"💰 <b>Сумма:</b> {int(order.total_amount)} ₽\n"
        message += f"📊 <b>Статус:</b> {status_text}\n"
        message += f"📅 <b>Дата заказа:</b> {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        if order.processed_at:
            message += f"✅ <b>Дата выполнения:</b> {order.processed_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        if order.video_links:
            message += f"\n🔗 <b>Ссылки на видео:</b>\n"
            for video_type, link in order.video_links.items():
                message += f"   • {video_type}: {link}\n"
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад к заказам", callback_data="view_orders")],
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
