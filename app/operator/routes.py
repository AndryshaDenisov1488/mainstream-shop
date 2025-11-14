from flask import render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from app.operator import bp
from app.utils.decorators import role_required
from app.models import Order, Event, User, db, VideoType
from sqlalchemy import desc, or_, and_, select
from sqlalchemy.orm import joinedload
import logging
from app.utils.order_status import expand_status_filter
from app.utils.datetime_utils import moscow_now_naive

logger = logging.getLogger(__name__)


def _apply_order_search_filter(query, search_term: str):
    """Apply common search filters for order listings."""
    if not search_term:
        return query
    term = search_term.strip()
    if not term:
        return query
    filters = [
        Order.generated_order_number.contains(term),
        Order.contact_email.contains(term),
    ]
    try:
        filters.append(Order.id == int(term))
    except (ValueError, TypeError):
        pass
    return query.filter(or_(*filters))

OPERATOR_VISIBLE_STATUSES = [
    'paid',
    'processing',
    'awaiting_info',
    'ready',
    'links_sent',
    'completed',
    'completed_partial_refund',
    'refund_required',
    'refunded_partial',
    'refunded_full',
    'cancelled_manual',
    'cancelled_unpaid',
]

OPERATOR_ACTIVE_STATUSES = [
    'processing',
    'awaiting_info',
]

OPERATOR_READY_STATUSES = [
    'ready',
    'links_sent',
]

@bp.route('/dashboard')
@login_required
@role_required('OPERATOR')
def dashboard():
    """Operator dashboard"""
    # Get statistics for operator - only paid orders
    # Новые заказы - только оплаченные заказы без оператора
    new_orders = Order.query.filter(
        Order.status == 'paid',
        Order.operator_id.is_(None)
    ).count()
    
    # В обработке - заказы в работе у операторов
    processing_orders = Order.query.filter(
        Order.status.in_(['processing', 'awaiting_info', 'ready']),
        Order.operator_id == current_user.id
    ).count()
    
    # Get all orders with pagination
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    search = request.args.get('search', '', type=str).strip()
    
    query = Order.query.filter(
        or_(
            Order.operator_id == current_user.id,
            and_(Order.operator_id.is_(None), Order.status == 'paid')
        ),
        Order.status.in_(OPERATOR_VISIBLE_STATUSES),
    )
    
    status_values = [s for s in expand_status_filter(status_filter) if s in OPERATOR_VISIBLE_STATUSES]
    if status_values:
        query = query.filter(Order.status.in_(status_values))
    
    query = _apply_order_search_filter(query, search)
    
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
    from app.models import OrderChat, ChatMessage
    unread_counts = {}
    total_counts = {}
    order_ids = [order.id for order in orders.items]
    if order_ids:
        chats = OrderChat.query.filter(OrderChat.order_id.in_(order_ids)).all()
        chat_dict = {chat.order_id: chat for chat in chats}
        # Get total message counts for all chats
        chat_ids = [chat.id for chat in chats]
        if chat_ids:
            from sqlalchemy import func
            message_counts = db.session.query(
                ChatMessage.chat_id,
                func.count(ChatMessage.id).label('total')
            ).filter(ChatMessage.chat_id.in_(chat_ids)).group_by(ChatMessage.chat_id).all()
            message_counts_dict = {chat_id: total for chat_id, total in message_counts}
        else:
            message_counts_dict = {}
        
        for order in orders.items:
            chat = chat_dict.get(order.id)
            if chat:
                try:
                    unread_counts[order.id] = chat.get_unread_count_for_user(current_user.id)
                    total_counts[order.id] = message_counts_dict.get(chat.id, 0)
                except Exception:
                    unread_counts[order.id] = 0
                    total_counts[order.id] = 0
            else:
                unread_counts[order.id] = 0
                total_counts[order.id] = 0
    else:
        unread_counts = {}
        total_counts = {}
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    return render_template('operator/dashboard.html',
                         new_orders=new_orders,
                         processing_orders=processing_orders,
                         orders=orders,
                         status_filter=status_filter,
                         search=search,
                         unread_counts=unread_counts,
                         total_counts=total_counts,
                         video_types_dict=video_types_dict)


@bp.route('/new-orders')
@login_required
@role_required('OPERATOR')
def new_orders():
    """New orders - only paid orders that need to be taken by operator"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str).strip()
    query = Order.query.filter(
        Order.status == 'paid',
        Order.operator_id.is_(None)
    )
    query = _apply_order_search_filter(query, search)
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/new_orders.html', orders=orders, search=search)


@bp.route('/processing-orders')
@login_required
@role_required('OPERATOR')
def processing_orders():
    """Processing orders assigned to the current operator"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str).strip()
    
    # ✅ Eager loading для избежания N+1 запросов
    query = Order.query.filter(
        Order.status.in_(OPERATOR_ACTIVE_STATUSES),
        Order.operator_id == current_user.id,
    ).options(
        joinedload(Order.event),
        joinedload(Order.category),
        joinedload(Order.athlete),
        joinedload(Order.operator),
        joinedload(Order.customer)
    )
    query = _apply_order_search_filter(query, search)
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/processing_orders.html', orders=orders, search=search)


@bp.route('/ready-orders')
@login_required
@role_required('OPERATOR')
def ready_orders():
    """Ready orders - orders prepared or with links already sent"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str).strip()
    query = Order.query.filter(
        Order.status.in_(OPERATOR_READY_STATUSES),
        Order.operator_id == current_user.id
    )
    query = _apply_order_search_filter(query, search)
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/ready_orders.html', orders=orders, search=search)


@bp.route('/completed-orders')
@login_required
@role_required('OPERATOR')
def completed_orders():
    """Completed orders for operator"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str).strip()
    query = Order.query.filter(
        Order.status.in_(['completed', 'completed_partial_refund']),
        Order.operator_id == current_user.id
    )
    query = _apply_order_search_filter(query, search)
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/completed_orders.html', orders=orders, search=search)

@bp.route('/orders/<int:order_id>/take')
@login_required
@role_required('OPERATOR')
def take_order(order_id):
    """Take order for processing"""
    try:
        import time
        import random
        from sqlalchemy.exc import OperationalError
        
        max_retries = 5
        retry_delay = 0.1  # Start with 100ms
        
        for attempt in range(max_retries):
            try:
                stmt = select(Order).where(Order.id == order_id).with_for_update()
                order = db.session.scalar(stmt)
                if not order:
                    db.session.rollback()
                    abort(404)
                
                if order.operator_id and order.operator_id != current_user.id:
                    db.session.rollback()
                    flash('Заказ уже взят другим оператором', 'error')
                    return redirect(url_for('operator.new_orders'))
                
                if order.status != 'paid':
                    db.session.rollback()
                    flash('Можно взять в работу только оплаченные заказы', 'error')
                    return redirect(url_for('operator.new_orders'))
                
                order.status = 'processing'
                order.operator_id = current_user.id
                order.processed_at = moscow_now_naive()
                db.session.commit()
                flash('Заказ взят в обработку', 'success')
                break  # Success, exit retry loop
            except OperationalError as e:
                if 'database is locked' in str(e).lower() and attempt < max_retries - 1:
                    db.session.rollback()
                    wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                    logger.warning(f'Database locked in take_order, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                else:
                    db.session.rollback()
                    logger.error(f'Error taking order after {attempt + 1} attempts: {str(e)}')
                    raise
        else:
            flash('Не удалось взять заказ в обработку. Попробуйте еще раз.', 'error')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error taking order: {str(e)}')
        flash('Ошибка при взятии заказа', 'error')
    
    return redirect(url_for('operator.new_orders'))


@bp.route('/orders/<int:order_id>/complete')
@login_required
@role_required('OPERATOR')
def complete_order(order_id):
    """Complete order"""
    order = Order.query.get_or_404(order_id)
    
    if order.operator_id != current_user.id:
        flash('У вас нет прав на этот заказ', 'error')
        return redirect(url_for('operator.ready_orders'))
    
    if order.status != 'links_sent':
        flash('Завершить можно только заказ со статусом "Ссылки отправлены"', 'error')
        return redirect(url_for('operator.ready_orders'))
    
    if not order.video_links:
        flash('Нельзя завершить заказ, пока не добавлены ссылки на видео', 'error')
        return redirect(url_for('operator.ready_orders'))
    
    try:
        import time
        import random
        from sqlalchemy.exc import OperationalError
        from app.utils.datetime_utils import moscow_now_naive
        
        order.status = 'completed'
        order.processed_at = moscow_now_naive()
        
        # ✅ Retry логика для обработки "database is locked"
        max_retries = 5
        retry_delay = 0.1  # Start with 100ms
        
        for attempt in range(max_retries):
            try:
                db.session.commit()
                break  # Success, exit retry loop
            except OperationalError as e:
                if 'database is locked' in str(e).lower() and attempt < max_retries - 1:
                    db.session.rollback()
                    wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                    logger.warning(f'Database locked in complete_order, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                    # Re-apply changes after rollback
                    order.status = 'completed'
                    order.processed_at = moscow_now_naive()
                else:
                    db.session.rollback()
                    logger.error(f'Error completing order after {attempt + 1} attempts: {str(e)}')
                    raise
        
        flash('Заказ завершен', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error completing order: {str(e)}')
        flash('Ошибка при завершении заказа', 'error')
    
    return redirect(url_for('operator.processing_orders'))

@bp.route('/orders/<int:order_id>')
@login_required
@role_required('OPERATOR')
def order_detail(order_id):
    """Order detail page for operator"""
    order = Order.query.get_or_404(order_id)
    
    # Check if operator has access to this order
    if order.operator_id and order.operator_id != current_user.id:
        flash('У вас нет доступа к этому заказу', 'error')
        return redirect(url_for('operator.dashboard'))
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    return render_template('operator/order_detail.html', order=order, video_types_dict=video_types_dict)
@bp.route('/orders/<int:order_id>/upload-links', methods=['GET', 'POST'])
@login_required
@role_required('OPERATOR')
def upload_video_links(order_id):
    """Upload video links for order"""
    order = Order.query.get_or_404(order_id)
    
    # Check if operator has access to this order
    if order.operator_id and order.operator_id != current_user.id:
        flash('У вас нет доступа к этому заказу', 'error')
        return redirect(url_for('operator.dashboard'))
    
    if request.method == 'POST':
        try:
            # Get video links from form
            video_links = {}
            
            # Process each video type
            for key, value in request.form.items():
                if key.startswith('video_link_') and value.strip():
                    video_type_id = key.replace('video_link_', '')
                    video_links[video_type_id] = value.strip()
            
            if not video_links:
                flash('Необходимо указать хотя бы одну ссылку на видео', 'error')
                return redirect(url_for('operator.upload_video_links', order_id=order_id))
            
            # Lock order row to avoid concurrent modifications
            stmt = select(Order).where(Order.id == order_id).with_for_update()
            locked_order = db.session.scalar(stmt)
            if not locked_order:
                db.session.rollback()
                abort(404)
            order = locked_order
            
            if order.operator_id and order.operator_id != current_user.id:
                db.session.rollback()
                flash('Заказ уже закреплен за другим оператором', 'error')
                return redirect(url_for('operator.dashboard'))
            
            # Update order with video links
            import time
            import random
            from sqlalchemy.exc import OperationalError
            from app.utils.datetime_utils import moscow_now_naive
            from app.models import OrderChat, ChatMessage
            
            order.video_links = video_links
            order.status = 'links_sent'  # Mark as links sent
            order.processed_at = moscow_now_naive()
            
            # If no operator assigned, assign current operator
            if not order.operator_id:
                order.operator_id = current_user.id
            
            # Create or get chat before commit
            chat = order.chat
            if not chat:
                chat = OrderChat(order_id=order_id)
                db.session.add(chat)
            
            # ✅ Retry логика для обработки "database is locked"
            max_retries = 5
            retry_delay = 0.1  # Start with 100ms
            
            for attempt in range(max_retries):
                try:
                    db.session.commit()
                    break  # Success, exit retry loop
                except OperationalError as e:
                    if 'database is locked' in str(e).lower() and attempt < max_retries - 1:
                        db.session.rollback()
                        wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                        logger.warning(f'Database locked in upload_video_links, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                        time.sleep(wait_time)
                        # Re-apply changes after rollback
                        order.video_links = video_links
                        order.status = 'links_sent'
                        order.processed_at = moscow_now_naive()
                        if not order.operator_id:
                            order.operator_id = current_user.id
                        chat = order.chat
                        if not chat:
                            chat = OrderChat(order_id=order_id)
                            db.session.add(chat)
                    else:
                        db.session.rollback()
                        logger.error(f'Error uploading video links after {attempt + 1} attempts: {str(e)}')
                        raise
            
            # ✅ Отправка email и уведомлений ПОСЛЕ коммита (не блокирует транзакцию)
            try:
                from app.utils.email import send_order_ready_notification
                
                # Add system message to chat (отдельная транзакция)
                try:
                    system_message = ChatMessage(
                        chat_id=chat.id,
                        sender_id=current_user.id,
                        message="Ссылки на видео отправлены клиенту",
                        message_type='system'
                    )
                    db.session.add(system_message)
                    db.session.commit()
                except Exception as e:
                    logger.warning(f"Failed to add system message to chat: {e}")
                    db.session.rollback()
                
                # Send notification to mom/admin
                send_order_ready_notification(order)
                
                # Send video links to client via Telegram if registered
                try:
                    from app.utils.telegram_notifier import send_video_links_notification
                    send_video_links_notification(order)
                except Exception as e:
                    logger.error(f"Failed to send video links via Telegram: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to send notifications: {e}")
            
            flash('Ссылки на видео успешно отправлены клиенту!', 'success')
            return redirect(url_for('operator.order_detail', order_id=order_id))
            
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при загрузке ссылок: ' + str(e), 'error')
    
    # Get video types for this order
    video_types = VideoType.query.filter(VideoType.id.in_(order.video_types)).all()
    
    return render_template('operator/upload_links.html', order=order, video_types=video_types)

@bp.route('/statistics')
@login_required
@role_required('OPERATOR')
def statistics():
    """Operator statistics and earnings"""
    # Get all completed orders for this operator
    completed_orders = Order.query.filter(
        Order.operator_id == current_user.id,
        Order.status.in_([
            'links_sent',
            'completed',
            'completed_partial_refund',
            'refunded_partial',
            'refunded_full',
        ])
    ).options(
        joinedload(Order.event),
        joinedload(Order.category),
        joinedload(Order.athlete)
    ).order_by(desc(Order.created_at)).all()
    
    # Get all video types
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    # Calculate earnings
    total_earnings = 0
    orders_earnings = []
    sport_videos_count = 0
    tv_videos_count = 0
    
    for order in completed_orders:
        if not order.video_types:
            continue
        
        # ✅ Исключаем заказы с полным возвратом из расчета заработка
        # Полный возврат означает отмену заказа - оператор не должен получать за это оплату
        if order.status in ['refunded_full', 'refunded_partial']:
            # Добавляем в список для отображения в таблице, но с нулевым заработком
            orders_earnings.append({
                'order': order,
                'earnings': 0,
                'sport_count': 0,
                'tv_count': 0
            })
            continue
            
        order_earnings = 0
        sport_count = 0
        tv_count = 0
        
        # Count video types in this order
        for video_type_id in order.video_types:
            if not video_type_id:
                continue
                
            video_type = video_types_dict.get(str(video_type_id))
            if not video_type:
                continue
            
            # Determine if it's sport or TV video
            video_name_lower = video_type.name.lower()
            # Проверяем наличие "2 проката" - это считается как 2 видео
            is_two_runs = '2 проката' in video_name_lower or '2 прокат' in video_name_lower
            
            if 'спорт' in video_name_lower:
                if is_two_runs:
                    sport_count += 2  # 2 проката = 2 видео
                else:
                    sport_count += 1
            elif 'тв' in video_name_lower or 'tv' in video_name_lower:
                if is_two_runs:
                    tv_count += 2  # 2 проката = 2 видео
                else:
                    tv_count += 1
        
        # Calculate earnings for this order
        # Каждое спорт видео = 100₽ (независимо от количества)
        order_earnings += sport_count * 100
        
        # Каждое ТВ видео = 300₽ (независимо от количества)
        order_earnings += tv_count * 300
        
        if order_earnings > 0:
            total_earnings += order_earnings
            sport_videos_count += sport_count
            tv_videos_count += tv_count
            
            orders_earnings.append({
                'order': order,
                'earnings': order_earnings,
                'sport_count': sport_count,
                'tv_count': tv_count
            })
    
    # Statistics by period (this month, last month, all time)
    from datetime import datetime, timedelta
    from app.utils.datetime_utils import moscow_now_naive
    
    now = moscow_now_naive()
    first_day_this_month = datetime(now.year, now.month, 1)
    first_day_last_month = (first_day_this_month - timedelta(days=1)).replace(day=1)
    
    # This month earnings
    this_month_orders = [oe for oe in orders_earnings if oe['order'].created_at >= first_day_this_month]
    this_month_earnings = sum(oe['earnings'] for oe in this_month_orders)
    
    # Last month earnings
    last_month_orders = [oe for oe in orders_earnings 
                        if oe['order'].created_at >= first_day_last_month 
                        and oe['order'].created_at < first_day_this_month]
    last_month_earnings = sum(oe['earnings'] for oe in last_month_orders)
    
    return render_template('operator/statistics.html',
                         total_earnings=total_earnings,
                         this_month_earnings=this_month_earnings,
                         last_month_earnings=last_month_earnings,
                         orders_earnings=orders_earnings,
                         sport_videos_count=sport_videos_count,
                         tv_videos_count=tv_videos_count,
                         total_orders=len(orders_earnings),
                         video_types_dict=video_types_dict)
