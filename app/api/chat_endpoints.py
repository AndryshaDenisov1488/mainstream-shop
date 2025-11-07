"""
API endpoints for order chat functionality
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from datetime import datetime

from app.utils.decorators import role_required
from app.utils.datetime_utils import moscow_now_naive
from app.models import Order, OrderChat, ChatMessage, User, db
from app.utils.email import send_chat_notification_email

bp = Blueprint('chat_api', __name__, url_prefix='/chat')

@bp.route('/order/<int:order_id>/messages', methods=['GET'])
@login_required
@role_required('OPERATOR', 'MOM', 'ADMIN')
def get_chat_messages(order_id):
    """Get chat messages for an order"""
    order = Order.query.get_or_404(order_id)
    
    # Check access rights
    if not _has_chat_access(order, current_user):
        return jsonify({'error': 'Нет доступа к чату этого заказа'}), 403
    
    # Get or create chat
    chat = OrderChat.query.filter_by(order_id=order_id).first()
    if not chat:
        chat = OrderChat(order_id=order_id)
        db.session.add(chat)
        db.session.commit()
    
    # Get messages with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    messages = chat.messages.order_by(ChatMessage.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Mark messages as read for current user
    chat.mark_messages_as_read(current_user.id, commit=True)
    
    return jsonify({
        'success': True,
        'messages': [{
            'id': msg.id,
            'sender_name': msg.sender.full_name,
            'sender_role': msg.sender.role,
            'message': msg.message,
            'message_type': msg.message_type,
            'created_at': msg.created_at.isoformat(),
            'attachment_name': msg.attachment_name,
            'attachment_path': msg.attachment_path
        } for msg in reversed(messages.items)],
        'has_prev': messages.has_prev,
        'has_next': messages.has_next,
        'page': page,
        'total': messages.total
    })

@bp.route('/order/<int:order_id>/send', methods=['POST'])
@login_required
@role_required('OPERATOR', 'MOM', 'ADMIN')
def send_chat_message(order_id):
    """Send a message to order chat"""
    try:
        current_app.logger.info(f"Chat message send attempt: order_id={order_id}, user_id={current_user.id}, user_role={current_user.role}")
        
        order = Order.query.get_or_404(order_id)
        
        # Check access rights
        if not _has_chat_access(order, current_user):
            current_app.logger.warning(f"Chat access denied: order_id={order_id}, user_id={current_user.id}")
            return jsonify({'error': 'Нет доступа к чату этого заказа'}), 403
        
        # Get or create chat
        chat = OrderChat.query.filter_by(order_id=order_id).first()
        if not chat:
            chat = OrderChat(order_id=order_id)
            db.session.add(chat)
            db.session.commit()
            current_app.logger.info(f"Created new chat for order_id={order_id}")
        
        message_text = request.form.get('message', '').strip()
        current_app.logger.debug(f"Message text length: {len(message_text) if message_text else 0}")
        
        # Handle file attachment
        attachment_path = None
        attachment_name = None
        
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename:
                # ✅ Проверка типа файла
                if not _is_allowed_file(file.filename):
                    return jsonify({'error': 'Недопустимый тип файла'}), 400
                
                # ✅ Проверка размера файла
                file.seek(0, 2)  # Seek to end
                file_size = file.tell()
                file.seek(0)  # Reset
                
                max_file_size = current_app.config.get('MAX_CHAT_FILE_SIZE', 10 * 1024 * 1024)
                if file_size > max_file_size:
                    return jsonify({
                        'error': f'Файл слишком большой (максимум {max_file_size // 1024 // 1024}MB)'
                    }), 400
                
                # ✅ Создание директории с абсолютным путем
                upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                order_dir = os.path.join(upload_folder, 'chat', str(order_id))
                os.makedirs(order_dir, exist_ok=True)
                
                # ✅ Нормализация пути для защиты от path traversal
                abs_order_dir = os.path.abspath(order_dir)
                
                # ✅ Генерация безопасного имени файла
                filename = secure_filename(file.filename)
                from app.utils.datetime_utils import moscow_now_naive
                timestamp = moscow_now_naive().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                
                filepath = os.path.join(abs_order_dir, filename)
                
                # ✅ Дополнительная проверка path traversal
                if not filepath.startswith(abs_order_dir):
                    return jsonify({'error': 'Небезопасный путь к файлу'}), 400
                
                file.save(filepath)
                
                attachment_path = os.path.join(str(order_id), filename)
                attachment_name = file.filename
        
        # Validate: must have either message or attachment
        if not message_text and not attachment_path:
            return jsonify({'error': 'Сообщение или файл обязательны'}), 400
        
        if message_text and len(message_text) > 5000:
            return jsonify({'error': 'Сообщение слишком длинное (максимум 5000 символов)'}), 400
        
        # Create message
        message = ChatMessage(
            chat_id=chat.id,
            sender_id=current_user.id,
            message=message_text,
            attachment_path=attachment_path,
            attachment_name=attachment_name
        )
        
        db.session.add(message)
        
        # Update chat last message time
        chat.last_message_at = moscow_now_naive()
        
        try:
            db.session.commit()
            current_app.logger.info(f"Chat message saved: message_id={message.id}, order_id={order_id}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to save chat message: {e}", exc_info=True)
            return jsonify({'error': f'Ошибка при сохранении сообщения: {str(e)}'}), 500
        
        # Send notifications to other participants
        try:
            _send_chat_notifications(chat, message, current_user)
        except Exception as e:
            current_app.logger.error(f"Failed to send chat notifications: {e}", exc_info=True)
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'sender_name': current_user.full_name,
                'sender_role': current_user.role,
                'message': message.message,
                'message_type': message.message_type,
                'created_at': message.created_at.isoformat(),
                'attachment_name': message.attachment_name,
                'attachment_path': message.attachment_path
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Error in send_chat_message: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'Произошла ошибка при отправке сообщения: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/unread-count', methods=['GET'])
@login_required
@role_required('OPERATOR', 'MOM', 'ADMIN')
def get_unread_count(order_id):
    """Get unread message count for an order chat"""
    order = Order.query.get_or_404(order_id)
    
    # Check access rights
    if not _has_chat_access(order, current_user):
        return jsonify({'error': 'Нет доступа к чату этого заказа'}), 403
    
    chat = OrderChat.query.filter_by(order_id=order_id).first()
    if not chat:
        return jsonify({'success': True, 'unread_count': 0})
    
    unread_count = chat.get_unread_count_for_user(current_user.id)
    return jsonify({'success': True, 'unread_count': unread_count})

@bp.route('/order/<int:order_id>/mark-read', methods=['POST'])
@login_required
@role_required('OPERATOR', 'MOM', 'ADMIN')
def mark_messages_read(order_id):
    """Mark all messages in chat as read"""
    order = Order.query.get_or_404(order_id)
    
    # Check access rights
    if not _has_chat_access(order, current_user):
        return jsonify({'error': 'Нет доступа к чату этого заказа'}), 403
    
    chat = OrderChat.query.filter_by(order_id=order_id).first()
    if chat:
        chat.mark_messages_as_read(current_user.id, commit=True)
    
    return jsonify({'success': True})

def _has_chat_access(order, user):
    """Check if user has access to order chat"""
    # Admin has access to all chats
    if user.role == 'ADMIN':
        return True
    
    # MOM has access to all chats
    if user.role == 'MOM':
        return True
    
    # Operator has access only to assigned orders
    if user.role == 'OPERATOR':
        return order.operator_id == user.id or order.operator_id is None
    
    return False

def _is_allowed_file(filename):
    """Check if file type is allowed"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def _send_chat_notifications(chat, message, sender):
    """Send email notifications for new chat message"""
    # Get other participants
    participants = []
    
    # Add MOM users
    moms = User.query.filter_by(role='MOM', is_active=True).all()
    participants.extend([mom for mom in moms if mom.id != sender.id])
    
    # Add assigned operator
    if chat.order.operator_id and chat.order.operator_id != sender.id:
        operator = User.query.get(chat.order.operator_id)
        if operator and operator.is_active:
            participants.append(operator)
    
    # Add admin users
    admins = User.query.filter_by(role='ADMIN', is_active=True).all()
    participants.extend([admin for admin in admins if admin.id != sender.id])
    
    # Send notifications
    for participant in participants:
        try:
            send_chat_notification_email(participant, chat.order, message, sender)
        except Exception as e:
            current_app.logger.error(f"Failed to send notification to {participant.email}: {e}")

@bp.route('/order/<int:order_id>/add-system-message', methods=['POST'])
@login_required
@role_required('OPERATOR', 'MOM', 'ADMIN')
def add_system_message(order_id):
    """Add system message to chat (for status changes, etc.)"""
    order = Order.query.get_or_404(order_id)
    
    # Check access rights
    if not _has_chat_access(order, current_user):
        return jsonify({'error': 'Нет доступа к чату этого заказа'}), 403
    
    message_text = request.json.get('message', '').strip()
    if not message_text:
        return jsonify({'error': 'Сообщение не может быть пустым'}), 400
    
    # Get or create chat
    chat = OrderChat.query.filter_by(order_id=order_id).first()
    if not chat:
        chat = OrderChat(order_id=order_id)
        db.session.add(chat)
        db.session.commit()
    
    # Create system message
    message = ChatMessage(
        chat_id=chat.id,
        sender_id=current_user.id,
        message=message_text,
        message_type='system'
    )
    
    db.session.add(message)
    chat.last_message_at = moscow_now_naive()
    db.session.commit()
    
    return jsonify({'success': True, 'message_id': message.id})
