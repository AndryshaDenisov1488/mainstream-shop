from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.operator import bp
from app.utils.decorators import role_required
from app.models import Order, Event, User, db, VideoType
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
import logging

logger = logging.getLogger(__name__)

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
        Order.status.in_(['processing', 'ready', 'links_sent'])
    ).count()
    
    # Get all orders with pagination
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    search = request.args.get('search', '', type=str)
    
    query = Order.query.filter(
        (Order.operator_id == current_user.id) | (Order.operator_id.is_(None)),
        Order.status.in_(['paid', 'processing', 'ready', 'links_sent', 'completed'])
    )
    
    if status_filter:
        query = query.filter(Order.status == status_filter)
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search))
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
    orders = Order.query.filter(
        Order.status == 'paid',
        Order.operator_id.is_(None)
    ).order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/new_orders.html', orders=orders)


@bp.route('/processing-orders')
@login_required
@role_required('OPERATOR')
def processing_orders():
    """Processing orders - orders where money is not yet accepted"""
    page = request.args.get('page', 1, type=int)
    
    # ✅ Eager loading для избежания N+1 запросов
    query = Order.query.filter(
        Order.status.in_(['processing', 'awaiting_info', 'links_sent', 'refund_required'])
    ).options(
        joinedload(Order.event),
        joinedload(Order.category),
        joinedload(Order.athlete),
        joinedload(Order.operator),
        joinedload(Order.customer)
    )
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/processing_orders.html', orders=orders)


@bp.route('/ready-orders')
@login_required
@role_required('OPERATOR')
def ready_orders():
    """Ready orders - orders with links sent"""
    page = request.args.get('page', 1, type=int)
    orders = Order.query.filter(
        Order.status == 'links_sent',
        Order.operator_id == current_user.id
    ).order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/ready_orders.html', orders=orders)


@bp.route('/completed-orders')
@login_required
@role_required('OPERATOR')
def completed_orders():
    """Completed orders for operator"""
    page = request.args.get('page', 1, type=int)
    orders = Order.query.filter(
        Order.status.in_(['completed', 'completed_partial_refund']),
        Order.operator_id == current_user.id
    ).order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('operator/completed_orders.html', orders=orders)

@bp.route('/orders/<int:order_id>/take')
@login_required
@role_required('OPERATOR')
def take_order(order_id):
    """Take order for processing"""
    order = Order.query.get_or_404(order_id)
    
    if order.status != 'paid':
        flash('Можно взять в работу только оплаченные заказы', 'error')
        return redirect(url_for('operator.new_orders'))
    
    try:
        order.status = 'processing'
        order.operator_id = current_user.id
        db.session.commit()
        
        flash('Заказ взят в обработку', 'success')
    except Exception as e:
        db.session.rollback()
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
    
    try:
        order.status = 'completed'
        db.session.commit()
        
        flash('Заказ завершен', 'success')
    except Exception as e:
        db.session.rollback()
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
            
            # Update order with video links
            order.video_links = video_links
            order.status = 'links_sent'  # Mark as links sent
            from app.utils.datetime_utils import moscow_now_naive
            order.processed_at = moscow_now_naive()
            
            # If no operator assigned, assign current operator
            if not order.operator_id:
                order.operator_id = current_user.id
            
            db.session.commit()
            
            # Add system message to chat
            try:
                from app.models import OrderChat, ChatMessage
                from app.utils.email import send_order_ready_notification
                
                # Create or get chat
                chat = order.chat
                if not chat:
                    chat = OrderChat(order_id=order_id)
                    db.session.add(chat)
                    db.session.commit()
                
                # Add system message
                system_message = ChatMessage(
                    chat_id=chat.id,
                    sender_id=current_user.id,
                    message="Ссылки на видео отправлены клиенту",
                    message_type='system'
                )
                db.session.add(system_message)
                db.session.commit()
                
                # Send notification to mom/admin
                send_order_ready_notification(order)
                
                # Send video links to client via Telegram if registered
                try:
                    from app.utils.telegram_notifier import send_video_links_notification
                    send_video_links_notification(order)
                except Exception as e:
                    logger.error(f"Failed to send video links via Telegram: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to add chat message or send notification: {e}")
            
            flash('Ссылки на видео успешно отправлены клиенту!', 'success')
            return redirect(url_for('operator.order_detail', order_id=order_id))
            
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при загрузке ссылок: ' + str(e), 'error')
    
    # Get video types for this order
    video_types = VideoType.query.filter(VideoType.id.in_(order.video_types)).all()
    
    return render_template('operator/upload_links.html', order=order, video_types=video_types)
