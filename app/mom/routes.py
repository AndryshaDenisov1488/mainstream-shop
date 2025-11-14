from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.mom import bp
from app.utils.decorators import role_required
from app.models import Order, Event, User, VideoType, Payment, db
from sqlalchemy import desc, func
from sqlalchemy.orm import joinedload
from datetime import datetime
import logging
from app.utils.order_status import expand_status_filter, get_status_filter_choices

logger = logging.getLogger(__name__)


def _get_chat_counts(order_items, current_user_id):
    """Return unread and total chat message counts for order list."""
    unread_counts = {}
    total_counts = {}
    order_ids = [order.id for order in order_items]

    if not order_ids:
        return unread_counts, total_counts

    from app.models import OrderChat, ChatMessage

    chats = OrderChat.query.filter(OrderChat.order_id.in_(order_ids)).all()
    chat_dict = {chat.order_id: chat for chat in chats}
    chat_ids = [chat.id for chat in chats]

    message_counts_dict = {}
    if chat_ids:
        message_counts = db.session.query(
            ChatMessage.chat_id,
            func.count(ChatMessage.id).label('total')
        ).filter(ChatMessage.chat_id.in_(chat_ids)).group_by(ChatMessage.chat_id).all()
        message_counts_dict = {chat_id: total for chat_id, total in message_counts}

    for order in order_items:
        chat = chat_dict.get(order.id)
        if chat:
            try:
                unread_counts[order.id] = chat.get_unread_count_for_user(current_user_id)
            except Exception:
                unread_counts[order.id] = 0
            total_counts[order.id] = message_counts_dict.get(chat.id, 0)
        else:
            unread_counts[order.id] = 0
            total_counts[order.id] = 0

    return unread_counts, total_counts

@bp.route('/dashboard')
@login_required
@role_required('MOM')
def dashboard():
    """Mom dashboard"""
    # Get statistics for mom
    NEED_PAYMENT_STATUSES = ['links_sent', 'completed_partial_refund']
    need_payment = Order.query.filter(Order.status.in_(NEED_PAYMENT_STATUSES)).count()
    
    # Нужно уточнить доп детали - заказы в статусе awaiting_info
    need_details = Order.query.filter_by(status='awaiting_info').count()
    
    # Требуется возврат - заказы со статусом refund_required (частичный или полный)
    full_refund = Order.query.filter_by(status='refund_required').count()
    
    # Get all orders with pagination (like in orders page)
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    search = request.args.get('search', '', type=str)
    
    query = Order.query
    
    if status_filter:
        normalized_statuses = expand_status_filter(status_filter) or [status_filter]
        query = query.filter(Order.status.in_(normalized_statuses))
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.id.cast(db.String).contains(search))
        )
    
    # ✅ Eager loading для избежания N+1 запросов
    query = query.options(
        joinedload(Order.event),
        joinedload(Order.category),
        joinedload(Order.athlete),
        joinedload(Order.operator)
    )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get chat message counts for each order
    unread_counts, total_counts = _get_chat_counts(orders.items, current_user.id)
    
    # Get video types for display
    from app.models import VideoType
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    return render_template('mom/dashboard.html', 
                         need_payment=need_payment,
                         need_details=need_details,
                         full_refund=full_refund,
                         orders=orders,
                         status_filter=status_filter,
                         status_choices=get_status_filter_choices(),
                         search=search,
                         unread_counts=unread_counts,
                         total_counts=total_counts,
                         video_types_dict=video_types_dict)

@bp.route('/orders')
@login_required
@role_required('MOM')
def orders():
    """All orders for mom"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    search = request.args.get('search', '', type=str)
    
    query = Order.query
    
    if status_filter:
        normalized_statuses = expand_status_filter(status_filter) or [status_filter]
        query = query.filter(Order.status.in_(normalized_statuses))
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.id.cast(db.String).contains(search))
        )
    
    # ✅ Eager loading для избежания N+1 запросов
    query = query.options(
        joinedload(Order.event),
        joinedload(Order.category),
        joinedload(Order.athlete),
        joinedload(Order.operator)
    )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    unread_counts, total_counts = _get_chat_counts(orders.items, current_user.id)
    
    return render_template(
        'mom/orders.html',
        orders=orders,
        status_filter=status_filter,
        status_choices=get_status_filter_choices(),
        search=search,
        video_types_dict=video_types_dict,
        unread_counts=unread_counts,
        total_counts=total_counts
    )

@bp.route('/pending-orders')
@login_required
@role_required('MOM')
def pending_orders():
    """Pending orders for mom"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    
    query = Order.query.filter(Order.status.in_(['checkout_initiated', 'awaiting_payment']))
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.id.cast(db.String).contains(search))
        )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('mom/pending_orders.html', orders=orders, search=search)

@bp.route('/events')
@login_required
@role_required('MOM')
def events():
    """Events management for mom"""
    page = request.args.get('page', 1, type=int)
    events = Event.query.order_by(desc(Event.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get statistics for each event
    event_stats = {}
    for event in events.items:
        orders = Order.query.filter_by(event_id=event.id).all()
        event_stats[event.id] = {
            'total_orders': len(orders),
            'pending_orders': len([o for o in orders if o.status in ['checkout_initiated', 'awaiting_payment']]),
            'processing_orders': len([o for o in orders if o.status == 'processing']),
            'completed_orders': len([o for o in orders if o.status == 'completed']),
            'cancelled_orders': len([o for o in orders if o.status.in_(['cancelled_unpaid', 'cancelled_manual'])]),
            'refund_required_orders': len([o for o in orders if o.status == 'refund_required']),
            'total_revenue': sum(o.total_amount for o in orders if o.status == 'completed'),
            'refund_reasons': {}
        }
        
        # Get refund reasons
        refund_orders = [o for o in orders if o.status == 'refund_required' or o.status in ['cancelled_unpaid', 'cancelled_manual']]
        for order in refund_orders:
            if order.operator_comment:
                reason = order.operator_comment[:50] + '...' if len(order.operator_comment) > 50 else order.operator_comment
                event_stats[event.id]['refund_reasons'][reason] = event_stats[event.id]['refund_reasons'].get(reason, 0) + 1
    
    return render_template('mom/events.html', events=events, event_stats=event_stats)

@bp.route('/reports')
@login_required
@role_required('MOM')
def reports():
    """Reports for mom"""
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # Get date range (last 30 days)
    from app.utils.datetime_utils import moscow_now_naive
    end_date = moscow_now_naive()
    start_date = end_date - timedelta(days=30)
    
    # Get orders statistics
    total_orders = Order.query.count()
    orders_last_month = Order.query.filter(Order.created_at >= start_date).count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).scalar() or 0
    
    # Get orders by status
    orders_by_status = db.session.query(
        Order.status,
        func.count(Order.id)
    ).group_by(Order.status).all()
    
    # Get top events by orders
    top_events = db.session.query(
        Event.name,
        func.count(Order.id).label('order_count')
    ).join(Order).group_by(Event.id).order_by(
        func.count(Order.id).desc()
    ).limit(5).all()
    
    return render_template('mom/reports.html',
                         total_orders=total_orders,
                         orders_last_month=orders_last_month,
                         total_revenue=total_revenue,
                         orders_by_status=orders_by_status,
                         top_events=top_events)

@bp.route('/orders/<int:order_id>')
@login_required
@role_required('MOM')
def order_detail(order_id):
    """Order detail page for mom"""
    order = Order.query.get_or_404(order_id)
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    return render_template('mom/order_detail.html', order=order, video_types_dict=video_types_dict)

@bp.route('/events/<int:event_id>')
@login_required
@role_required('MOM')
def event_detail(event_id):
    """Event detail page for mom"""
    event = Event.query.get_or_404(event_id)
    return render_template('mom/event_detail.html', event=event)


@bp.route('/orders/<int:order_id>/send-links', methods=['POST'])
@login_required
@role_required('MOM')
def send_links(order_id):
    """Send video links to customer"""
    order = Order.query.get_or_404(order_id)
    
    allowed_statuses = ['completed', 'links_sent', 'completed_partial_refund', 'refund_required']
    if order.status not in allowed_statuses:
        return jsonify({'success': False, 'error': 'Ссылки можно отправить только после выполнения заказа'})
    
    try:
        # Send video links email to customer
        from app.utils.email import send_video_links_email
        send_video_links_email(order)
        
        # Send Telegram notification with links (if user has telegram_id)
        try:
            from app.utils.telegram_notifier import send_video_links_notification
            send_video_links_notification(order)
        except Exception as e:
            logger.warning(f'Failed to send Telegram notification with links: {e}')
            # Don't fail the whole operation if Telegram notification fails
        
        # Update order status
        if order.status == 'completed':
            order.status = 'links_sent'
        db.session.commit()
        
        # Log action
        from app.models import AuditLog
        AuditLog.create_log(
            user_id=current_user.id,
            action='LINKS_SENT',
            resource_type='Order',
            resource_id=str(order.id),
            details={'method': 'mom_route'},
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({'success': True, 'message': 'Ссылки отправлены'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/orders/<int:order_id>/confirm-payment', methods=['POST'])
@login_required
@role_required('MOM')
def confirm_payment(order_id):
    """Confirm payment (charge money from authorized payment) - DEPRECATED: Use /api/order/<id>/capture instead"""
    # Redirect to proper API endpoint
    from flask import redirect, url_for
    return redirect(url_for('api.capture_payment', order_id=order_id), code=307)

@bp.route('/orders/<int:order_id>/resend-links', methods=['POST'])
@login_required
@role_required('MOM')
def resend_links(order_id):
    """Resend video links to customer with new email"""
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    
    allowed_statuses = ['completed', 'links_sent', 'completed_partial_refund', 'refund_required']
    if order.status not in allowed_statuses:
        return jsonify({'success': False, 'error': 'Ссылки можно отправить только после выполнения заказа'})
    
    email = data.get('email')
    message = data.get('message', '')
    
    if not email:
        return jsonify({'success': False, 'error': 'Email обязателен'})
    
    try:
        # Send video links email to new email address
        from app.utils.email import send_video_links_email
        # Temporarily update order email for sending
        original_email = order.contact_email
        order.contact_email = email
        send_video_links_email(order)
        
        # Send Telegram notification with links (if user has telegram_id)
        # Use original email to find user, but send notification anyway if new email matches a user
        try:
            from app.utils.telegram_notifier import send_video_links_notification
            send_video_links_notification(order)
        except Exception as e:
            logger.warning(f'Failed to send Telegram notification with links: {e}')
            # Don't fail the whole operation if Telegram notification fails
        # Restore original email
        order.contact_email = original_email
        
        return jsonify({'success': True, 'message': 'Ссылки отправлены на новый email'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/orders/<int:order_id>/refund', methods=['POST'])
@login_required
@role_required('MOM')
def refund_order(order_id):
    """Process refund for order"""
    order = Order.query.get_or_404(order_id)
    
    try:
        # Process refund through CloudPayments API
        from app.utils.cloudpayments import CloudPaymentsAPI
        
        # Find payment for this order
        payment = Payment.query.filter_by(order_id=order_id).first()
        if not payment:
            return jsonify({'success': False, 'error': 'Платеж не найден'})
        
        # Process refund
        cp_api = CloudPaymentsAPI()
        refund_result = cp_api.refund_payment(
            transaction_id=payment.cp_transaction_id,
            amount=None,  # Full refund
            user_id=current_user.id
        )
        
        if refund_result['success']:
            # Update order status based on refund type
            if refund_result.get('refund_amount') and float(refund_result['refund_amount']) < float(payment.amount):
                order.status = 'completed_partial_refund'
            else:
                order.status = 'refunded_full'
            db.session.commit()
            return jsonify({'success': True, 'message': 'Возврат выполнен'})
        else:
            return jsonify({'success': False, 'error': refund_result['error']})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/processing-orders')
@login_required
@role_required('MOM')
def processing_orders():
    """Orders in processing - taken by operators but links not sent"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    
    query = Order.query.filter(
        Order.status.in_(['processing', 'awaiting_info']),
        Order.operator_id.isnot(None)
    )
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.id.cast(db.String).contains(search))
        )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('mom/processing_orders.html', orders=orders, search=search)

@bp.route('/need-payment-orders')
@login_required
@role_required('MOM')
def need_payment_orders():
    """Orders where money needs to be accepted - links sent or partial refund required"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    
    query = Order.query.filter(
        Order.status.in_(['links_sent', 'completed_partial_refund'])
    )
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.id.cast(db.String).contains(search))
        )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('mom/need_payment_orders.html', orders=orders, search=search)

@bp.route('/need-details-orders')
@login_required
@role_required('MOM')
def need_details_orders():
    """Orders that need additional details clarification"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    
    query = Order.query.filter_by(status='awaiting_info')
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.id.cast(db.String).contains(search))
        )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('mom/need_details_orders.html', orders=orders, search=search)

@bp.route('/full-refund-orders')
@login_required
@role_required('MOM')
def full_refund_orders():
    """Orders requiring full refund"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    
    query = Order.query.filter_by(status='refund_required')
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.id.cast(db.String).contains(search))
        )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('mom/full_refund_orders.html', orders=orders, search=search)

@bp.route('/refund-statistics')
@login_required
@role_required('MOM')
def refund_statistics():
    """Refund statistics dashboard"""
    from datetime import timedelta
    from app.utils.datetime_utils import moscow_now_naive
    from sqlalchemy import func
    
    # Период для статистики (последние 30 дней)
    period_start = moscow_now_naive() - timedelta(days=30)
    
    # Все возвраты за последний месяц
    refunds_query = Payment.query.filter(
        Payment.status.in_(['refunded_partial', 'refunded_full']),
        Payment.created_at >= period_start
    )
    
    refunds = refunds_query.all()
    
    # Общая статистика
    total_refunds = len(refunds)
    total_refund_amount = sum(p.amount for p in refunds)
    
    # Группировка по статусу
    refunds_by_status = {
        'refunded_partial': 0,
        'refunded_full': 0
    }
    amount_by_status = {
        'refunded_partial': 0,
        'refunded_full': 0
    }
    
    for payment in refunds:
        refunds_by_status[payment.status] += 1
        amount_by_status[payment.status] += payment.amount
    
    # Заказы с возвратами
    orders_with_refunds = Order.query.filter(
        Order.status.in_(['refund_required', 'completed_partial_refund', 'cancelled_manual']),
        Order.created_at >= period_start
    ).all()
    
    # Причины возвратов (из комментариев заказов)
    refund_reasons = {}
    for order in orders_with_refunds:
        if order.comment:
            reason = order.comment[:50]  # Первые 50 символов
            refund_reasons[reason] = refund_reasons.get(reason, 0) + 1
    
    # Сортировка причин по частоте
    refund_reasons = dict(sorted(refund_reasons.items(), key=lambda x: x[1], reverse=True)[:10])
    
    stats = {
        'total_refunds': total_refunds,
        'total_amount': total_refund_amount,
        'by_status': refunds_by_status,
        'amount_by_status': amount_by_status,
        'orders_with_refunds': len(orders_with_refunds),
        'refund_reasons': refund_reasons,
        'period_days': 30
    }
    
    return render_template('mom/refund_statistics.html', stats=stats, orders=orders_with_refunds)