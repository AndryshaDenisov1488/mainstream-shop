"""
Payment processing routes
Handles payment flow and order creation after successful payment
"""

from flask import request, redirect, url_for, flash, render_template, session, current_app
from flask_login import current_user
from app import db
from app.models import Order, User, Athlete, VideoType
from app.utils.cloudpayments import CloudPaymentsAPI
from app.utils.email import send_order_confirmation_email
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def register_payment_routes(bp):
    """Register payment processing routes"""
    
    @bp.route('/payment/process', methods=['POST'])
    def process_payment():
        """Process payment and create order after successful payment"""
        try:
            # Get cart from session
            cart = session.get('cart', {})
            
            if not cart:
                flash('Ваша корзина пуста', 'error')
                return redirect(url_for('main.checkout'))
            
            # Get form data
            contact_email = request.form.get('contact_email')
            contact_phone = request.form.get('contact_phone')
            comment = request.form.get('comment', '')
            payment_method = request.form.get('payment_method', 'card')
            
            if not contact_email:
                flash('Email обязателен для оформления заказа', 'error')
                return redirect(url_for('main.checkout'))
            
            # Clean up any existing pending orders from session
            pending_order_id = session.get('pending_order_id')
            if pending_order_id:
                old_order = Order.query.get(pending_order_id)
                if old_order and old_order.status == 'awaiting_payment':
                    db.session.delete(old_order)
                    db.session.commit()
                session.pop('pending_order_id', None)
            
            # Create order numbers
            order_number = Order.generate_order_number()
            generated_order_number = Order.generate_human_order_number()
            
            # Process all items in cart
            cart_items = []
            total_amount = 0
            video_types = []
            
            for item_id, quantity in cart.items():
                try:
                    athlete_id, video_type_id = map(int, item_id.split('_'))
                    athlete = Athlete.query.get(athlete_id)
                    video_type = VideoType.query.get(video_type_id)
                    
                    if athlete and video_type:
                        item_total = video_type.price * quantity
                        total_amount += item_total
                        
                        cart_items.append({
                            'athlete': athlete,
                            'video_type': video_type,
                            'quantity': quantity,
                            'total': item_total
                        })
                        
                        # Add video type to order
                        for _ in range(quantity):
                            video_types.append(video_type_id)
                    else:
                        flash(f'Товар {item_id} не найден', 'error')
                        return redirect(url_for('main.checkout'))
                except (ValueError, AttributeError):
                    flash(f'Ошибка в данных товара {item_id}', 'error')
                    return redirect(url_for('main.checkout'))
            
            if not cart_items:
                flash('Корзина пуста или содержит некорректные товары', 'error')
                return redirect(url_for('main.checkout'))
            
            # Get contact information
            contact_first_name = request.form.get('contact_first_name', '').strip()
            contact_last_name = request.form.get('contact_last_name', '').strip()
            
            # Get or create customer user
            customer_id = None
            if current_user.is_authenticated:
                customer_id = current_user.id
            else:
                # Check if user already exists
                existing_user = User.query.filter_by(email=contact_email).first()
                if existing_user:
                    customer_id = existing_user.id
                else:
                    # Create new user
                    import secrets
                    password = secrets.token_urlsafe(12)
                    
                    new_user = User(
                        email=contact_email,
                        full_name=f"{contact_first_name} {contact_last_name}".strip(),
                        phone=contact_phone,
                        role='CUSTOMER',
                        is_active=True
                    )
                    new_user.set_password(password)
                    
                    db.session.add(new_user)
                    db.session.flush()  # Get the ID
                    customer_id = new_user.id
            
            # Clean up any existing pending orders for this customer
            existing_pending_orders = Order.query.filter_by(
                customer_id=customer_id,
                status='awaiting_payment'
            ).all()
            
            for old_order in existing_pending_orders:
                db.session.delete(old_order)
            
            db.session.commit()  # Clean up old orders first
            
            # Create order in database FIRST
            # Create order in database with pending_payment status
            # For multiple items, we need to handle this differently
            # For now, we'll create separate orders for each athlete
            orders = []
            for item in cart_items:
                order = Order(
                    order_number=Order.generate_order_number(),
                    generated_order_number=Order.generate_human_order_number(),
                    customer_id=customer_id,
                    event_id=item['athlete'].category.event_id,
                    category_id=item['athlete'].category_id,
                    athlete_id=item['athlete'].id,
                    video_types=[item['video_type'].id] * item['quantity'],
                    total_amount=item['total'],
                    status='awaiting_payment',  # Order awaiting payment
                    contact_email=contact_email,
                    contact_phone=contact_phone,
                    contact_first_name=contact_first_name,
                    contact_last_name=contact_last_name,
                    comment=comment
                )
                orders.append(order)
                db.session.add(order)
            
            # For simplicity, we'll work with the first order
            main_order = orders[0]
            
            try:
                db.session.commit()  # Save orders to get IDs
            except Exception as e:
                db.session.rollback()
                logger.error(f'Error creating order: {str(e)}')
                flash('Ошибка создания заказа. Попробуйте еще раз.', 'error')
                return redirect(url_for('main.checkout'))
            
            # Store order ID in session for success/failure handling
            session['pending_order_id'] = main_order.id
            
            # Create CloudPayments widget URL using order object
            cp_api = CloudPaymentsAPI()
            payment_data = cp_api.create_payment_widget_data(main_order, payment_method)
            
            if not payment_data:
                logger.error(f'Failed to create payment data for order {main_order.order_number}')
                flash('Ошибка создания платежной формы. Проверьте настройки CloudPayments.', 'error')
                return redirect(url_for('main.checkout'))
            
            # Get video types for template
            video_types = {vt.id: vt for vt in VideoType.query.all()}
            
            # Render checkout page with CloudPayments widget
            return render_template('main/checkout.html', 
                                 cart_items=cart_items,
                                 total_price=total_amount,
                                 payment_data=payment_data,
                                 payment_method=payment_method,
                                 show_payment_widget=True)
            
        except Exception as e:
            logger.error(f'Error processing payment: {str(e)}')
            flash('Произошла ошибка при обработке заказа', 'error')
            return redirect(url_for('main.checkout'))
    
    @bp.route('/payment/success')
    def payment_success():
        """Handle successful payment"""
        try:
            # Get pending order ID from session
            pending_order_id = session.get('pending_order_id')
            
            if not pending_order_id:
                flash('Заказ не найден', 'error')
                return redirect(url_for('main.index'))
            
            # Get order from database
            order = Order.query.get(pending_order_id)
            
            if not order:
                flash('Заказ не найден', 'error')
                return redirect(url_for('main.index'))
            
            # Clear cart and session data
            session.pop('cart', None)
            session.pop('pending_order_id', None)
            
            # Send order confirmation email
            try:
                send_order_confirmation_email(order)
                logger.info(f'Order confirmation email sent for order {order.generated_order_number}')
            except Exception as e:
                logger.error(f'Failed to send order confirmation email: {e}')
            
            flash('Заказ успешно оформлен! Оператор скоро свяжется с вами.', 'success')
            return render_template('main/order_success.html', order=order)
            
        except Exception as e:
            logger.error(f'Error handling payment success: {str(e)}')
            flash('Произошла ошибка при обработке заказа', 'error')
            return redirect(url_for('main.index'))
    
    @bp.route('/payment/failure')
    def payment_failure():
        """Handle failed payment"""
        try:
            # Get pending order ID from session
            pending_order_id = session.get('pending_order_id')
            
            if pending_order_id:
                # Delete the pending order from database
                order = Order.query.get(pending_order_id)
                if order and order.status == 'awaiting_payment':
                    db.session.delete(order)
                    db.session.commit()
            
            # Clear session data
            session.pop('pending_order_id', None)
            
            flash('Оплата не была завершена. Попробуйте еще раз.', 'error')
            return render_template('main/payment_failure.html')
            
        except Exception as e:
            logger.error(f'Error handling payment failure: {str(e)}')
            flash('Произошла ошибка', 'error')
            return redirect(url_for('main.index'))
    
    @bp.route('/payment/return/<order_number>')
    def payment_return(order_number):
        """Handle payment return (user came back from payment page)"""
        try:
            # Check if order was created (payment was successful)
            order = Order.query.filter_by(order_number=order_number).first()
            
            if order:
                # Payment was successful, redirect to success page
                return redirect(url_for('main.payment_success'))
            else:
                # Payment was not successful, redirect to failure page
                return redirect(url_for('main.payment_failure'))
                
        except Exception as e:
            logger.error(f'Error handling payment return: {str(e)}')
            return redirect(url_for('main.index'))

