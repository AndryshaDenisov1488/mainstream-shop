from flask import render_template, redirect, url_for, flash, request, jsonify, session, current_app
from flask_login import login_required, current_user
from app.main import bp
from app.main.payment_routes import register_payment_routes
from app import db
from app.models import Event, Category, Athlete, VideoType, Order
from app.utils.decorators import staff_required
from sqlalchemy import desc

@bp.route('/')
def index():
    """Main page"""
    # Get active events with categories and athletes count
    events = Event.query.filter_by(is_active=True).order_by(desc(Event.start_date)).limit(6).all()
    
    # Get video types with prices
    video_types = VideoType.query.filter_by(is_active=True).all()
    
    # Statistics for staff
    stats = {}
    if current_user.is_authenticated and current_user.role in ['ADMIN', 'MOM', 'OPERATOR']:
        stats = {
            'total_orders': Order.query.count(),
            'pending_orders': Order.query.filter(Order.status.in_(['checkout_initiated', 'awaiting_payment'])).count(),
            'processing_orders': Order.query.filter_by(status='processing').count(),
            'completed_orders': Order.query.filter_by(status='completed').count(),
        }
    
    return render_template('main/index.html', 
                         events=events, 
                         video_types=video_types,
                         stats=stats)

@bp.route('/shop')
def shop():
    """Shop page - list of tournaments"""
    page = request.args.get('page', 1, type=int)
    events = Event.query.filter_by(is_active=True)\
                       .order_by(desc(Event.start_date))\
                       .paginate(page=page, per_page=12, error_out=False)
    
    # Get video types for pricing display
    video_types = VideoType.query.filter_by(is_active=True).all()
    
    return render_template('main/shop.html', events=events, video_types=video_types)

@bp.route('/about')
def about():
    """About page"""
    return render_template('main/about.html')

@bp.route('/tournament/<int:event_id>')
def tournament(event_id):
    """Tournament details page"""
    event = Event.query.get_or_404(event_id)
    
    if not event.is_active:
        flash('Этот турнир недоступен для заказа', 'error')
        return redirect(url_for('main.shop'))
    
    # Get categories with athletes count
    categories = Category.query.filter_by(event_id=event_id)\
                              .order_by(Category.name).all()
    
    # Add athletes count to each category
    for category in categories:
        category.athletes_count = Athlete.query.filter_by(category_id=category.id).count()
    
    # Get video types for pricing display
    video_types = VideoType.query.filter_by(is_active=True).all()
    
    return render_template('main/tournament.html', event=event, categories=categories, video_types=video_types)

@bp.route('/tournament/<int:event_id>/category/<int:category_id>')
def category_athletes(event_id, category_id):
    """Category athletes page"""
    event = Event.query.get_or_404(event_id)
    category = Category.query.filter_by(id=category_id, event_id=event_id).first_or_404()
    
    if not event.is_active:
        flash('Этот турнир недоступен для заказа', 'error')
        return redirect(url_for('main.shop'))
    
    # Get athletes in this category
    athletes = Athlete.query.filter_by(category_id=category_id)\
                           .order_by(Athlete.name).all()
    
    # Get video types
    video_types = VideoType.query.filter_by(is_active=True).all()
    
    return render_template('main/category_athletes.html', 
                         event=event, 
                         category=category, 
                         athletes=athletes,
                         video_types=video_types)

@bp.route('/api/athlete/<int:athlete_id>/details')
def athlete_details(athlete_id):
    """Get athlete details for modal"""
    athlete = Athlete.query.get_or_404(athlete_id)
    
    return jsonify({
        'id': athlete.id,
        'name': athlete.name,
        'birth_date': athlete.birth_date.strftime('%d.%m.%Y') if athlete.birth_date else None,
        'gender': athlete.gender,
        'club_name': athlete.club_name,
        'is_pair': athlete.is_pair,
        'partner_name': athlete.partner_name,
        'category': athlete.category.name,
        'event': athlete.category.event.name
    })

@bp.route('/api/video-types')
def get_video_types():
    """Get all active video types for frontend"""
    video_types = VideoType.query.filter_by(is_active=True).all()
    
    return jsonify([{
        'id': vt.id,
        'name': vt.name,
        'description': vt.description,
        'price': float(vt.price)
    } for vt in video_types])

@bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('main/contact.html')

# Register payment routes
register_payment_routes(bp)

@bp.route('/contact/send', methods=['POST'])
def send_contact_form():
    """Handle contact form submission"""
    from flask_mail import Message
    from app import mail
    from app.utils.settings import get_contact_email
    
    try:
        data = request.get_json()
        
        # Get contact email from settings
        contact_email = get_contact_email()
        
        # Create email message
        msg = Message(
            subject=f"Сообщение с сайта: {data.get('subject', 'Вопрос')}",
            recipients=[contact_email],
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        
        msg.body = f"""
Имя: {data.get('name')}
Email: {data.get('email')}
Тема: {data.get('subject')}

Сообщение:
{data.get('message')}
        """
        
        # Send email
        mail.send(msg)
        
        return jsonify({'success': True, 'message': 'Сообщение отправлено!'})
        
    except Exception as e:
        current_app.logger.error(f'Contact form error: {str(e)}')
        return jsonify({'success': False, 'message': 'Ошибка отправки сообщения'}), 500

@bp.route('/cart')
def cart():
    """Shopping cart page"""
    # Get cart from session
    cart = session.get('cart', {})
    
    # Get cart items with full details
    cart_items = []
    total_price = 0
    
    for item_id, quantity in cart.items():
        try:
            # Parse item_id to get athlete_id and video_type_id
            athlete_id, video_type_id = map(int, item_id.split('_'))
            
            athlete = Athlete.query.get(athlete_id)
            video_type = VideoType.query.get(video_type_id)
            
            if athlete and video_type:
                item_total = video_type.price * quantity
                total_price += item_total
                
                cart_items.append({
                    'id': item_id,
                    'athlete': athlete,
                    'video_type': video_type,
                    'quantity': quantity,
                    'total': item_total
                })
        except (ValueError, AttributeError):
            continue
    
    return render_template('main/cart.html', 
                         cart_items=cart_items, 
                         total_price=total_price)

@bp.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    """Add item to cart"""
    data = request.get_json()
    athlete_id = data.get('athlete_id')
    video_type_id = data.get('video_type_id')
    quantity = data.get('quantity', 1)
    
    if not athlete_id or not video_type_id:
        return jsonify({'success': False, 'error': 'Неверные параметры'})
    
    # Get cart from session
    cart = session.get('cart', {})
    item_key = f"{athlete_id}_{video_type_id}"
    
    if item_key in cart:
        cart[item_key] += quantity
    else:
        cart[item_key] = quantity
    
    session['cart'] = cart
    session.modified = True  # Mark session as modified
    
    # Calculate total items in cart
    total_items = sum(cart.values())
    
    return jsonify({
        'success': True, 
        'cart_count': total_items
    })

@bp.route('/api/cart/remove', methods=['POST'])
def remove_from_cart():
    """Remove item from cart"""
    data = request.get_json()
    item_id = data.get('item_id')
    
    if not item_id:
        return jsonify({'success': False, 'error': 'Неверные параметры'})
    
    # Get cart from session
    cart = session.get('cart', {})
    
    if item_id in cart:
        del cart[item_id]
        session['cart'] = cart
        session.modified = True  # Mark session as modified
        
        # Calculate total items in cart
        total_items = sum(cart.values())
        
        return jsonify({
            'success': True, 
            'message': 'Товар удален из корзины',
            'cart_count': total_items
        })
    else:
        return jsonify({'success': False, 'error': 'Товар не найден в корзине'})

@bp.route('/api/cart/update', methods=['POST'])
def update_cart():
    """Update item quantity in cart"""
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)
    
    if not item_id:
        return jsonify({'success': False, 'error': 'Неверные параметры'})
    
    if quantity <= 0:
        return remove_from_cart()
    
    # Get cart from session
    cart = session.get('cart', {})
    cart[item_id] = quantity
    session['cart'] = cart
    
    # Calculate total items in cart
    total_items = sum(cart.values())
    
    return jsonify({
        'success': True, 
        'message': 'Корзина обновлена',
        'cart_count': total_items
    })

@bp.route('/api/cart/count')
def get_cart_count():
    """Get total number of items in cart"""
    cart = session.get('cart', {})
    total_items = sum(cart.values())
    
    return jsonify({
        'success': True,
        'count': total_items
    })

@bp.route('/checkout', methods=['GET'])
def checkout():
    """Checkout page"""
    # Get cart from session
    cart = session.get('cart', {})
    
    # Get cart from session
    
    if not cart:
        flash('Ваша корзина пуста', 'warning')
        return redirect(url_for('main.cart'))
    
    # Get cart items with full details
    cart_items = []
    total_price = 0
    
    for item_id, quantity in cart.items():
        try:
            # Parse item_id to get athlete_id and video_type_id
            athlete_id, video_type_id = map(int, item_id.split('_'))
            
            athlete = Athlete.query.get(athlete_id)
            video_type = VideoType.query.get(video_type_id)
            
            if athlete and video_type:
                item_total = video_type.price * quantity
                total_price += item_total
                
                cart_items.append({
                    'id': item_id,
                    'athlete': athlete,
                    'video_type': video_type,
                    'quantity': quantity,
                    'total': item_total
                })
        except (ValueError, AttributeError):
            continue
    
    return render_template('main/checkout.html', 
                         cart_items=cart_items, 
                         total_price=total_price)


@bp.route('/order-success/<int:order_id>')
def order_success(order_id):
    """Order success page"""
    order = Order.query.get_or_404(order_id)
    
    # Check if user has access to this order
    if current_user.is_authenticated and order.customer_id != current_user.id:
        flash('У вас нет прав на просмотр этого заказа', 'error')
        return redirect(url_for('main.shop'))
    
    return render_template('main/order_success.html', order=order)

@bp.route('/track-order', methods=['GET', 'POST'])
def track_order():
    """Track order by email and order number"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        order_number = request.form.get('order_number', '').strip()
        
        if not email or not order_number:
            flash('Пожалуйста, заполните все поля', 'error')
            return render_template('main/track_order.html')
        
        # Find order by email and order number
        order = Order.query.filter(
            Order.contact_email == email,
            Order.generated_order_number == order_number
        ).first()
        
        if order:
            return render_template('main/order_tracking.html', order=order)
        else:
            flash('Заказ не найден. Проверьте правильность введенных данных.', 'error')
            return render_template('main/track_order.html')
    
    return render_template('main/track_order.html')

@bp.route('/privacy-policy')
def privacy_policy():
    """Privacy policy page"""
    return render_template('main/privacy_policy.html')

@bp.route('/terms-of-use')
def terms_of_use():
    """Terms of use page"""
    return render_template('main/terms_of_use.html')
