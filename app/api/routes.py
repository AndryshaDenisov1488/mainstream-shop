from flask import request, jsonify, current_app
from config import Config
from flask_login import login_required, current_user
from app import db
from app.api import bp
from app.api.cloudpayments_endpoints import register_cloudpayments_routes
from app.models import Order, Payment, User, AuditLog, VideoType
from app.utils.decorators import admin_or_mom_required, role_required
from app.utils.cloudpayments import CloudPaymentsAPI
from app.utils.email import send_order_confirmation_email
from app.utils.datetime_utils import moscow_now_naive
import copy
import json
import logging
import base64
import requests
import random
import time
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)
def _execute_db_operation_with_retry(operation_fn, context: str):
    """Execute a DB write operation with retry logic for sqlite 'database is locked' errors."""
    max_retries = 5
    retry_delay = 0.1

    for attempt in range(max_retries):
        try:
            operation_fn()
            db.session.commit()
            return
        except OperationalError as exc:
            db.session.rollback()
            if 'database is locked' in str(exc).lower() and attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(
                    f"Database locked while executing '{context}'. "
                    f"Retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
            else:
                logger.error(f"DB operation '{context}' failed after {attempt + 1} attempts: {exc}")
                raise

OPERATOR_MANAGEABLE_STATUSES = (
    'processing',
    'awaiting_info',
    'ready',
    'links_sent',
    'completed',
    'completed_partial_refund',
    'refund_required',
    'cancelled_unpaid',
    'cancelled_manual',
)

# DEPRECATED: Use /cloudpayments/webhook instead
# This route is kept for backward compatibility but may be removed
# @bp.route('/payment/webhook', methods=['POST'])
# def payment_webhook():
#     """Handle payment webhook from CloudPayments (DEPRECATED - use /cloudpayments/webhook)"""
#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({'error': 'No data provided'}), 400
#         
#         cp_api = CloudPaymentsAPI()
#         result = cp_api.process_webhook(data)
#         
#         if result['success']:
#             # For CloudPayments check notifications, return code: 0
#             if 'code' in result:
#                 return jsonify({'code': result['code']}), 200
#             else:
#                 return jsonify({'status': 'success'}), 200
#         else:
#             return jsonify({'error': result['error']}), 400
#             
#     except Exception as e:
#         logger.error(f'Webhook processing error: {str(e)}')
#         return jsonify({'error': 'Internal server error'}), 500

@bp.route('/payment/create', methods=['POST'])
def create_payment():
    """Create payment intent for order (CloudPayments widget data)"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        payment_method = data.get('payment_method', 'card')
        
        if not order_id:
            return jsonify({'success': False, 'error': 'Order ID required'}), 400
        
        order = Order.query.get_or_404(order_id)
        
        # Check if order is in correct status
        if order.status != 'checkout_initiated':
            return jsonify({'success': False, 'error': 'Order is not in checkout_initiated status'}), 409
        
        # Generate CloudPayments widget data
        try:
            cp_api = CloudPaymentsAPI()
            payment_data = cp_api.create_payment_widget_data(order, payment_method)
            
            if not payment_data:
                error_msg = 'Failed to create payment widget data'
                # Check if it's a configuration issue
                if not current_app.config.get('CLOUDPAYMENTS_PUBLIC_ID') or not current_app.config.get('CLOUDPAYMENTS_API_SECRET'):
                    error_msg = 'CloudPayments не настроен. Установите CLOUDPAYMENTS_PUBLIC_ID и CLOUDPAYMENTS_API_SECRET в .env файле'
                return jsonify({'success': False, 'error': error_msg}), 500
        except ValueError as e:
            # CloudPayments not configured
            logger.error(f'CloudPayments configuration error: {str(e)}')
            return jsonify({
                'success': False, 
                'error': 'CloudPayments не настроен. Установите CLOUDPAYMENTS_PUBLIC_ID и CLOUDPAYMENTS_API_SECRET в .env файле',
                'details': str(e)
            }), 500
        except Exception as cp_error:
            # Other CloudPayments errors
            logger.error(f'CloudPayments error: {str(cp_error)}', exc_info=True)
            return jsonify({
                'success': False,
                'error': f'Ошибка CloudPayments: {str(cp_error)}'
            }), 500
        
        def _set_awaiting_payment_status():
            fresh_order = Order.query.get(order.id)
            if not fresh_order:
                raise ValueError('Order not found during status update')
            fresh_order.status = 'awaiting_payment'
            fresh_order.payment_method = payment_method

        _execute_db_operation_with_retry(
            _set_awaiting_payment_status,
            'api.create_payment.awaiting_payment'
        )
        
        return jsonify({
            'success': True,
            'payment_data': payment_data
        })
        
    except Exception as e:
        logger.error(f'Create payment error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/payment/process', methods=['POST'])
def process_payment():
    """Process payment with cryptogram from CloudPayments Checkout"""
    try:
        data = request.get_json()
        cryptogram = data.get('cryptogram')
        amount = data.get('amount')
        currency = data.get('currency')
        description = data.get('description')
        invoice_id = data.get('invoiceId')
        email = data.get('email')
        order_id = data.get('orderId')
        payment_method = data.get('paymentMethod', 'card')
        
        if not all([cryptogram, amount, currency, invoice_id, email, order_id]):
            return jsonify({'success': False, 'error': 'Missing required payment data'}), 400
        
        # Get order
        order = Order.query.get_or_404(order_id)
        
        # Process payment with CloudPayments API
        cp_api = CloudPaymentsAPI()
        
        # Prepare payment data for API
        payment_data = {
            'Amount': float(amount),
            'Currency': currency,
            'IpAddress': request.remote_addr or '127.0.0.1',
            'CardCryptogramPacket': cryptogram,
            'InvoiceId': invoice_id,
            'Description': description,
            'Email': email,
            'Name': f"{order.contact_first_name} {order.contact_last_name}".strip() or 'Cardholder'
        }
        
        # Send payment to CloudPayments API
        auth_string = f"{cp_api.public_id}:{cp_api.api_secret}"
        auth_token = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Basic {auth_token}'
        }
        
        response = requests.post(
            f"{cp_api.base_url}/payments/cards/charge",
            headers=headers,
            json=payment_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('Success'):
                # Payment successful
                transaction_id = result.get('TransactionId')
                
                payment_payload = {
                    'order_id': order.id,
                    'cp_transaction_id': transaction_id,
                    'amount': float(amount),
                    'currency': currency,
                    'status': 'authorized',
                    'method': payment_method,
                    'email': email,
                    'raw_payload': result
                }

                def _persist_payment_and_update_order():
                    fresh_order = Order.query.get(order.id)
                    if not fresh_order:
                        raise ValueError('Order not found during payment persistence')
                    payment_record = Payment(**payment_payload)
                    db.session.add(payment_record)
                    fresh_order.status = 'paid'
                    fresh_order.paid_amount = float(amount)
                    fresh_order.payment_intent_id = transaction_id
                    fresh_order.payment_method = payment_method

                _execute_db_operation_with_retry(
                    _persist_payment_and_update_order,
                    'api.process_payment.persist'
                )
                
                logger.info(f'Payment successful for order {order.order_number}, transaction {transaction_id}')
                
                return jsonify({
                    'success': True,
                    'transaction_id': transaction_id,
                    'message': 'Payment processed successfully'
                })
            else:
                # Payment failed
                error_message = result.get('Message', 'Unknown error')
                logger.error(f'Payment failed for order {order.order_number}: {error_message}')
                
                return jsonify({
                    'success': False,
                    'error': error_message
                }), 400
        else:
            # HTTP error
            logger.error(f'Payment API error: {response.status_code} - {response.text}')
            
            return jsonify({
                'success': False,
                'error': f'Payment API error: {response.status_code}'
            }), 500
        
    except Exception as e:
        logger.error(f'Process payment error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/order/<int:order_id>/change-status', methods=['POST'])
@login_required
@admin_or_mom_required
def change_order_status(order_id):
    """Change order status"""
    try:
        import time
        import random
        from sqlalchemy.exc import OperationalError
        
        order = Order.query.get_or_404(order_id)
        
        data = request.get_json()
        new_status = data.get('status')
        operator_comment = data.get('comment', '')
        
        if not new_status:
            return jsonify({'success': False, 'error': 'Status required'}), 400
        
        # Validate status
        if new_status not in OPERATOR_MANAGEABLE_STATUSES:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        # Update order - save old status before changing
        old_status = order.status
        order.status = new_status
        if operator_comment:
            order.operator_comment = operator_comment
        
        if new_status in ['completed', 'completed_partial_refund', 'cancelled_manual']:
            order.processed_at = moscow_now_naive()
        
        # Если заказ отменяется, сохраняем причину
        if new_status == 'cancelled_manual':
            order.cancellation_reason = operator_comment
        
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
                    logger.warning(f'Database locked in change_order_status, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                    # Re-apply changes after rollback
                    order.status = new_status
                    if operator_comment:
                        order.operator_comment = operator_comment
                    if new_status in ['completed', 'completed_partial_refund', 'cancelled_manual']:
                        order.processed_at = moscow_now_naive()
                    if new_status == 'cancelled_manual':
                        order.cancellation_reason = operator_comment
                else:
                    db.session.rollback()
                    logger.error(f'Error changing order status after {attempt + 1} attempts: {str(e)}')
                    raise
        
        # ✅ Отправляем email ПОСЛЕ коммита (не блокирует транзакцию)
        if new_status == 'cancelled_manual':
            try:
                from app.utils.email import send_order_cancellation_email
                send_order_cancellation_email(order, operator_comment)
            except Exception as e:
                logger.error(f"Error sending cancellation email: {e}")
        
        # Log action
        AuditLog.create_log(
            user_id=current_user.id,
            action='ORDER_STATUS_CHANGE',
            resource_type='Order',
            resource_id=str(order.id),
            details={'old_status': old_status, 'new_status': new_status, 'comment': operator_comment},
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': f'Статус заказа изменен на {new_status}',
            'order': {
                'id': order.id,
                'status': order.status,
                'generated_order_number': order.generated_order_number
            }
        })
        
    except Exception as e:
        logger.error(f'Change order status error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/order/<int:order_id>/operator-change-status', methods=['POST'])
@login_required
@role_required('OPERATOR')
def operator_change_order_status(order_id):
    """Change order status by operator"""
    try:
        import time
        import random
        from sqlalchemy.exc import OperationalError
        
        order = Order.query.get_or_404(order_id)
        
        data = request.get_json()
        new_status = data.get('status')
        operator_comment = data.get('comment', '')
        
        if not new_status:
            return jsonify({'success': False, 'error': 'Status required'}), 400
        
        # Validate status
        valid_statuses = ['draft', 'checkout_initiated', 'awaiting_payment', 'paid', 'processing', 'awaiting_info', 'refund_required', 'ready', 'links_sent', 'completed', 'completed_partial_refund', 'cancelled_unpaid', 'cancelled_manual', 'refunded_partial', 'refunded_full']
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        # Update order - save old status before changing
        old_status = order.status
        order.status = new_status
        if operator_comment:
            order.operator_comment = operator_comment
        
        # Set operator if not set
        if not order.operator_id:
            order.operator_id = current_user.id
        
        if new_status in ['completed', 'completed_partial_refund', 'cancelled_unpaid', 'cancelled_manual', 'refunded_full', 'refunded_partial']:
            order.processed_at = moscow_now_naive()
        
        # Если заказ отменяется, сохраняем причину
        if new_status in ['cancelled_unpaid', 'cancelled_manual']:
            order.cancellation_reason = operator_comment
        
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
                    logger.warning(f'Database locked in operator_change_order_status, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                    # Re-apply changes after rollback
                    order.status = new_status
                    if operator_comment:
                        order.operator_comment = operator_comment
                    if not order.operator_id:
                        order.operator_id = current_user.id
                    if new_status in ['completed', 'completed_partial_refund', 'cancelled_unpaid', 'cancelled_manual', 'refunded_full', 'refunded_partial']:
                        order.processed_at = moscow_now_naive()
                    if new_status in ['cancelled_unpaid', 'cancelled_manual']:
                        order.cancellation_reason = operator_comment
                else:
                    db.session.rollback()
                    logger.error(f'Error changing order status by operator after {attempt + 1} attempts: {str(e)}')
                    raise
        
        # ✅ Отправляем email ПОСЛЕ коммита (не блокирует транзакцию)
        if new_status in ['cancelled_unpaid', 'cancelled_manual']:
            try:
                from app.utils.email import send_order_cancellation_email
                send_order_cancellation_email(order, operator_comment)
            except Exception as e:
                logger.error(f"Error sending cancellation email: {e}")
        
        # Add system message to chat
        try:
            from app.api.chat_endpoints import _add_status_change_message
            _add_status_change_message(order_id, new_status, operator_comment, current_user.id)
        except ImportError:
            logger.warning("Chat endpoints not available for status change message")
        
        # Log action
        AuditLog.create_log(
            user_id=current_user.id,
            action='ORDER_STATUS_CHANGE',
            resource_type='Order',
            resource_id=str(order.id),
            details={'old_status': old_status, 'new_status': new_status, 'comment': operator_comment},
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': f'Статус заказа изменен на {new_status}',
            'order': {
                'id': order.id,
                'status': order.status,
                'generated_order_number': order.generated_order_number
            }
        })
        
    except Exception as e:
        logger.error(f'Operator change order status error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/order/<int:order_id>/info', methods=['GET'])
@login_required
def get_order_info(order_id):
    """Get detailed order information"""
    try:
        order = Order.query.get_or_404(order_id)
        
        # Check access permissions
        if current_user.role not in ['ADMIN', 'MOM', 'OPERATOR']:
            if order.customer_id != current_user.id:
                return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Get video types
        video_types = VideoType.query.all()
        video_types_dict = {str(vt.id): vt for vt in video_types}
        
        # Prepare order data
        order_data = {
            'id': order.id,
            'generated_order_number': order.generated_order_number,
            'status': order.status,
            'contact_email': order.contact_email,
            'contact_first_name': order.contact_first_name,
            'contact_last_name': order.contact_last_name,
            'contact_phone': order.contact_phone,
            'operator_comment': order.operator_comment,
            'refund_reason': order.refund_reason,
            'comment': order.comment,
            'total_amount': float(order.total_amount),
            'paid_amount': float(order.paid_amount) if order.paid_amount else 0,
            'payment_method': order.payment_method,
            'payment_expires_at': order.payment_expires_at.isoformat() if order.payment_expires_at else None,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'video_types': order.video_types or [],
            'video_links': order.video_links or {},
            'video_types_info': {},
            'event': {
                'id': order.event.id if order.event else None,
                'name': order.event.name if order.event else 'Не указан'
            } if order.event else {'id': None, 'name': 'Не указан'},
            'category': {
                'id': order.category.id if order.category else None,
                'name': order.category.name if order.category else 'Не указана'
            } if order.category else {'id': None, 'name': 'Не указана'},
            'athlete': {
                'id': order.athlete.id if order.athlete else None,
                'name': order.athlete.name if order.athlete else 'Не указан'
            } if order.athlete else {'id': None, 'name': 'Не указан'},
            'customer': {
                'id': order.customer.id if order.customer else None,
                'full_name': order.customer.full_name if order.customer else None
            } if order.customer else {'id': None, 'full_name': None},
            'operator': {
                'id': order.operator.id if order.operator else None,
                'full_name': order.operator.full_name if order.operator else None
            } if order.operator else {'id': None, 'full_name': None},
            'processed_at': order.processed_at.isoformat() if order.processed_at else None
        }
        
        # Add video types info as array for JavaScript compatibility
        video_types_array = []
        if order.video_types:
            logger.info(f"Raw video_types for order {order.id}: {order.video_types}")
            
            # Filter out empty arrays and invalid values
            valid_video_types = []
            for item in order.video_types:
                logger.info(f"Processing item: {item}, type: {type(item)}")
                if item is not None and item != [] and item != [[]] and item != {}:
                    if isinstance(item, list):
                        # If it's a list, check if it contains valid IDs
                        for sub_item in item:
                            if sub_item is not None and sub_item != [] and sub_item != {}:
                                if isinstance(sub_item, list):
                                    valid_video_types.extend(sub_item)
                                else:
                                    valid_video_types.append(sub_item)
                    elif isinstance(item, dict):
                        # If it's a dict, check if it has valid properties
                        if 'id' in item and item['id'] is not None:
                            valid_video_types.append(item['id'])
                    else:
                        valid_video_types.append(item)
            
            logger.info(f"Valid video types for order {order.id}: {valid_video_types}")
            
            for video_type_id in valid_video_types:
                # Try both string and int keys
                vt = video_types_dict.get(str(video_type_id)) or video_types_dict.get(int(video_type_id))
                if vt:
                    video_types_array.append({
                        'id': vt.id,
                        'name': vt.name,
                        'description': vt.description,
                        'price': float(vt.price)
                    })
                    order_data['video_types_info'][str(video_type_id)] = {
                        'name': vt.name,
                        'description': vt.description,
                        'price': float(vt.price)
                    }
                else:
                    logger.warning(f"Video type with ID {video_type_id} not found in database")
        
        order_data['video_types'] = video_types_array
        
        # If no video types found but we have video_links, try to extract from there
        if not video_types_array and order.video_links:
            logger.info(f"No video_types found, trying to extract from video_links: {order.video_links}")
            for video_type_id in order.video_links.keys():
                vt = video_types_dict.get(str(video_type_id)) or video_types_dict.get(int(video_type_id))
                if vt:
                    video_types_array.append({
                        'id': vt.id,
                        'name': vt.name,
                        'description': vt.description,
                        'price': float(vt.price)
                    })
            order_data['video_types'] = video_types_array
        
        return jsonify({
            'success': True,
            'order': order_data
        })
        
    except Exception as e:
        logger.error(f'Get order info error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/order/<int:order_id>/send-links', methods=['POST'])
@login_required
def send_video_links_api(order_id):
    """Send video links via API"""
    try:
        order = Order.query.get_or_404(order_id)
        
        # Get data from JSON or form
        if request.is_json:
            data = request.get_json()
            video_links = data.get('video_links', {})
            customer_email = data.get('client_email', order.contact_email)
            customer_name = data.get('client_name', '')
            message = data.get('message', '')
            partial_refund = data.get('partial_refund', False)
            refund_comment = data.get('refund_comment', '')
        else:
            # Fallback to form data
            video_links = {}
            customer_email = request.form.get('customer_email', order.contact_email)
            customer_name = request.form.get('customer_name', '')
            message = request.form.get('message', '')
            partial_refund = request.form.get('partial_refund', False) == 'true'
            refund_comment = request.form.get('refund_comment', '')
            
            # Process each video type from form
            # Поддерживаем как старый формат (video_type_id), так и новый (video_type_id_index)
            for key, value in request.form.items():
                if key.startswith('video_link_') and value.strip():
                    field_key = key.replace('video_link_', '')
                    video_links[field_key] = value.strip()
        
        if not video_links:
            return jsonify({'success': False, 'error': 'Необходимо указать хотя бы одну ссылку на видео'}), 400
        
        final_video_links = copy.deepcopy(video_links)
        final_contact_email = customer_email
        final_first_name = order.contact_first_name
        final_last_name = order.contact_last_name

        if customer_name:
            name_parts = customer_name.strip().split(' ')
            if len(name_parts) >= 2:
                final_last_name = name_parts[0]
                final_first_name = ' '.join(name_parts[1:])
            elif len(name_parts) == 1:
                final_first_name = name_parts[0]

        base_operator_comment = order.operator_comment or ''
        partial_flag = '[ТРЕБУЕТСЯ ЧАСТИЧНЫЙ ВОЗВРАТ]'
        final_refund_reason = None

        if partial_refund:
            if base_operator_comment:
                if partial_flag not in base_operator_comment:
                    base_operator_comment = f'{base_operator_comment}\n{partial_flag}'
            else:
                base_operator_comment = partial_flag
            if refund_comment:
                final_refund_reason = refund_comment
        else:
            final_refund_reason = None

        if message:
            final_operator_comment = message
        else:
            final_operator_comment = base_operator_comment

        processed_at_value = moscow_now_naive()
        final_operator_id = order.operator_id or current_user.id

        def _apply_video_links_update():
            fresh_order = Order.query.get(order.id)
            if not fresh_order:
                raise ValueError('Order not found during send links update')
            fresh_order.video_links = final_video_links
            fresh_order.contact_email = final_contact_email
            fresh_order.contact_first_name = final_first_name
            fresh_order.contact_last_name = final_last_name
            fresh_order.status = 'links_sent'
            fresh_order.operator_comment = final_operator_comment
            fresh_order.refund_reason = final_refund_reason
            fresh_order.processed_at = processed_at_value
            if not fresh_order.operator_id and final_operator_id:
                fresh_order.operator_id = final_operator_id

        _execute_db_operation_with_retry(
            _apply_video_links_update,
            'api.send_video_links.update_order'
        )

        db.session.refresh(order)
        
        # Send email with links
        try:
            from app.utils.email import send_video_links_email
            send_video_links_email(order)
        except Exception as e:
            logger.error(f'Failed to send email: {e}')
            # Don't fail the whole operation if email fails
        
        # Send Telegram notification with links (if user has telegram_id)
        # ✅ 152-ФЗ: Не логируем email на уровне INFO
        logger.info(f"[API] About to send Telegram notification for order {order.id}")
        try:
            from app.utils.telegram_notifier import send_video_links_notification
            result = send_video_links_notification(order)
            logger.info(f"[API] Telegram notification result for order {order.id}: {result}")
        except Exception as e:
            logger.error(f'[API] Failed to send Telegram notification with links: {e}', exc_info=True)
            # Don't fail the whole operation if Telegram notification fails
        
        # Log action
        AuditLog.create_log(
            user_id=current_user.id,
            action='LINKS_SENT',
            resource_type='Order',
            resource_id=str(order.id),
            details={
                'video_links': video_links, 
                'message': message,
                'customer_email': customer_email,
                'partial_refund': partial_refund,
                'refund_comment': refund_comment if partial_refund else None
            },
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': 'Ссылки отправлены успешно'
        })
        
    except Exception as e:
        logger.error(f'Send video links error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка отправки ссылок: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/assign-operator', methods=['POST'])
@login_required
def assign_operator_api(order_id):
    """Assign operator to order (only for paid orders)"""
    try:
        from sqlalchemy import select
        from sqlalchemy.exc import OperationalError
        
        # Check if user has permission (admin, mom, or operator)
        if not (current_user.role == 'ADMIN' or current_user.role == 'MOM' or current_user.role == 'OPERATOR'):
            return jsonify({'success': False, 'error': 'Недостаточно прав'}), 403
        
        # ✅ ИСПОЛЬЗУЕМ SELECT FOR UPDATE для блокировки строки
        # Flask автоматически создает транзакцию для каждого request, поэтому
        # не используем db.session.begin() - это вызовет ошибку "transaction already begun"
        try:
            # Блокируем строку заказа для обновления (защита от race condition)
            stmt = select(Order).where(
                Order.id == order_id,
                Order.status == 'paid',
                Order.operator_id.is_(None)  # ✅ Проверяем, что оператор еще не назначен
            ).with_for_update()
            
            order = db.session.scalar(stmt)
            
            if not order:
                db.session.rollback()
                return jsonify({
                    'success': False, 
                    'error': 'Заказ недоступен (уже взят другим оператором или не оплачен)'
                }), 409
            
            # Проверка прав уже сделана выше
            # Назначаем оператора
            order.operator_id = current_user.id
            order.status = 'processing'
            order.processed_at = moscow_now_naive()
            
            # Коммитим транзакцию (Flask автоматически создал её для этого request)
            db.session.commit()
                
        except OperationalError as e:
            # Если произошла ошибка блокировки (редко, но возможно)
            db.session.rollback()
            logger.error(f'Database lock error assigning operator: {str(e)}')
            return jsonify({'success': False, 'error': 'Заказ уже обрабатывается другим оператором'}), 409
        
        # Логирование после успешного коммита
        AuditLog.create_log(
            user_id=current_user.id,
            action='OPERATOR_TOOK_ORDER',
            resource_type='Order',
            resource_id=str(order.id),
            details={
                'assigned_operator': current_user.full_name,
                'order_status': 'processing',
                'paid_amount': float(order.paid_amount)
            },
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            commit=True  # ✅ Коммитим отдельно, т.к. основная транзакция уже завершена
        )
        
        return jsonify({
            'success': True,
            'message': 'Заказ взят в работу успешно'
        })
        
    except Exception as e:
        logger.error(f'Assign operator error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка назначения оператора: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/capture', methods=['POST'])
@login_required
@role_required('MOM', 'ADMIN')
def capture_payment(order_id):
    """Capture (confirm) payment for mom"""
    try:
        order = Order.query.get_or_404(order_id)
        
        # Check if order can be captured
        if not order.can_be_captured_by_mom():
            return jsonify({'success': False, 'error': 'Заказ не может быть зачтен в текущем статусе'}), 409
        
        data = request.get_json()
        capture_amount = data.get('amount')
        
        if not capture_amount:
            return jsonify({'success': False, 'error': 'Сумма к зачету не указана'}), 400
        
        capture_amount = float(capture_amount)
        
        if capture_amount <= 0:
            return jsonify({'success': False, 'error': 'Сумма к зачету должна быть больше нуля'}), 400
        
        # Ищем платеж: сначала авторизованный (для capture), затем подтвержденный (для подтверждения получения денег)
        payment = order.payments.filter_by(status='authorized').first()
        is_already_confirmed = False
        
        if not payment:
            # Если нет авторизованного платежа, ищем подтвержденный
            payment = order.payments.filter_by(status='confirmed').first()
            if payment:
                is_already_confirmed = True
            else:
                return jsonify({'success': False, 'error': 'Платеж не найден (ни авторизованный, ни подтвержденный)'}), 404
        
        # Проверка суммы
        if capture_amount > float(payment.amount):
            return jsonify({
                'success': False, 
                'error': f'Сумма ({capture_amount}) не может превышать сумму платежа ({payment.amount})'
            }), 400
        
        if capture_amount > float(order.total_amount):
            return jsonify({
                'success': False, 
                'error': f'Сумма ({capture_amount}) не может превышать сумму заказа ({order.total_amount})'
            }), 400
        
        audit_entries = []
        new_order_status = order.status
        new_paid_amount = order.paid_amount
        new_payment_amount_override = None

        if is_already_confirmed:
            new_paid_amount = capture_amount
            if capture_amount < float(order.total_amount):
                new_order_status = 'completed_partial_refund'
            else:
                new_order_status = 'completed'

            audit_entries.append({
                'action': 'MOM_CONFIRMED_RECEIPT',
                'details': {
                    'confirmed_amount': capture_amount,
                    'total_amount': float(order.total_amount),
                    'transaction_id': payment.cp_transaction_id,
                    'payment_method': order.payment_method
                }
            })
        else:
            cp_api = CloudPaymentsAPI()
            if order.payment_method == 'card':
                is_partial_capture = capture_amount < float(order.total_amount)

                if is_partial_capture:
                    confirm_result = cp_api.confirm_payment(payment.cp_transaction_id, capture_amount)
                    if not confirm_result.get('success'):
                        return jsonify({'success': False, 'error': f'Ошибка подтверждения платежа: {confirm_result.get("error")}'}), 500
                    new_order_status = 'completed_partial_refund'
                    new_paid_amount = capture_amount
                    new_payment_amount_override = capture_amount
                    audit_entries.append({
                        'action': 'MOM_CAPTURED_PARTIAL',
                        'details': {
                            'captured_amount': capture_amount,
                            'refunded_amount': float(order.total_amount) - capture_amount,
                            'total_amount': float(order.total_amount),
                            'transaction_id': payment.cp_transaction_id,
                            'note': f'Принято {capture_amount}₽, остаток {float(order.total_amount) - capture_amount}₽ автоматически возвращен'
                        }
                    })
                else:
                    confirm_result = cp_api.confirm_payment(payment.cp_transaction_id)
                    if not confirm_result.get('success'):
                        return jsonify({'success': False, 'error': f'Ошибка подтверждения платежа: {confirm_result.get("error")}'}), 500
                    new_order_status = 'completed'
                    new_paid_amount = capture_amount
                    audit_entries.append({
                        'action': 'MOM_CAPTURED_FULL',
                        'details': {
                            'captured_amount': capture_amount,
                            'transaction_id': payment.cp_transaction_id
                        }
                    })
            else:
                new_paid_amount = capture_amount
                if capture_amount < float(order.total_amount):
                    new_order_status = 'completed_partial_refund'
                else:
                    new_order_status = 'completed'
                audit_entries.append({
                    'action': 'MOM_CAPTURED_SBP',
                    'details': {
                        'captured_amount': capture_amount,
                        'payment_method': 'sbp'
                    }
                })

        confirmed_at_value = moscow_now_naive()

        def _apply_capture_changes():
            fresh_order = Order.query.get(order.id)
            fresh_payment = Payment.query.get(payment.id)
            if not fresh_order or not fresh_payment:
                raise ValueError('Order or payment not found during capture persistence')
            fresh_order.status = new_order_status
            fresh_order.paid_amount = new_paid_amount
            fresh_payment.status = 'confirmed'
            fresh_payment.mom_confirmed = True
            fresh_payment.confirmed_at = confirmed_at_value
            fresh_payment.confirmed_by = current_user.id
            if new_payment_amount_override is not None:
                fresh_payment.amount = new_payment_amount_override
            for entry in audit_entries:
                AuditLog.create_log(
                    user_id=current_user.id,
                    action=entry['action'],
                    resource_type='Order',
                    resource_id=str(order.id),
                    details=entry['details'],
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent'),
                    commit=False
                )

        _execute_db_operation_with_retry(
            _apply_capture_changes,
            'api.capture_payment.persist'
        )
        
        return jsonify({
            'success': True,
            'message': f'Платеж зачтен на сумму {capture_amount} руб.',
            'captured_amount': capture_amount
        })
        
    except Exception as e:
        logger.error(f'Capture payment error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка зачета платежа: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/refund', methods=['POST'])
@login_required
@role_required('MOM', 'ADMIN')
def refund_payment(order_id):
    """Refund payment"""
    try:
        order = Order.query.get_or_404(order_id)
        
        data = request.get_json()
        refund_amount = data.get('amount')  # If None, full refund
        
        if refund_amount:
            refund_amount = float(refund_amount)
            if refund_amount <= 0:
                return jsonify({'success': False, 'error': 'Некорректная сумма возврата'}), 400
        
        # Find the payment - можно вернуть только confirmed платежи
        payment = order.payments.filter_by(status='confirmed').first()
        if not payment:
            # Проверим, есть ли authorized платежи (для них нужен void, не refund)
            authorized_payment = order.payments.filter_by(status='authorized').first()
            if authorized_payment:
                return jsonify({
                    'success': False, 
                    'error': 'Платеж еще не подтвержден. Используйте отмену платежа вместо возврата.'
                }), 400
            return jsonify({'success': False, 'error': 'Подтвержденный платеж не найден'}), 404
        
        cp_api = CloudPaymentsAPI()
        
        # ✅ Определяем сумму возврата
        if refund_amount is None:
            refund_amount = float(order.paid_amount or payment.amount)  # Полный возврат
        else:
            refund_amount = float(refund_amount)
        
        # ✅ Проверка: сумма возврата должна быть положительной
        if refund_amount <= 0:
            return jsonify({'success': False, 'error': 'Сумма возврата должна быть больше нуля'}), 400
        
        # ✅ Проверка: сумма возврата не должна превышать подтвержденную сумму платежа
        if refund_amount > float(payment.amount):
            return jsonify({
                'success': False, 
                'error': f'Сумма возврата ({refund_amount}) превышает подтвержденную сумму платежа ({payment.amount})'
            }), 400
        
        # ✅ Проверка: сумма возврата не должна превышать оплаченную сумму заказа
        if refund_amount > float(order.paid_amount or 0):
            return jsonify({
                'success': False, 
                'error': f'Сумма возврата ({refund_amount}) превышает оплаченную сумму заказа ({order.paid_amount})'
            }), 400
        
        # Perform refund через CloudPayments API
        refund_result = cp_api.refund_payment(payment.cp_transaction_id, refund_amount)
        if not refund_result.get('success'):
            return jsonify({'success': False, 'error': f'Ошибка возврата: {refund_result.get("error")}'}), 500
        
        # ✅ Определяем тип возврата и обновляем статусы
        original_paid_amount = float(order.paid_amount or 0)
        is_full_refund = refund_amount >= original_paid_amount

        if is_full_refund:
            new_order_status = 'refunded_full'
            new_payment_status = 'refunded_full'
            new_paid_amount = 0
            audit_entries = [{
                'user_id': current_user.id,
                'action': 'MOM_REFUNDED_FULL',
                'details': {
                    'refund_amount': original_paid_amount,
                    'transaction_id': payment.cp_transaction_id
                }
            }]
        else:
            new_order_status = 'completed_partial_refund'
            new_payment_status = 'refunded_partial'
            remaining_amount = original_paid_amount - refund_amount
            new_paid_amount = remaining_amount
            audit_entries = [{
                'user_id': current_user.id,
                'action': 'MOM_REFUNDED_PARTIAL',
                'details': {
                    'refund_amount': refund_amount,
                    'remaining_amount': remaining_amount,
                    'transaction_id': payment.cp_transaction_id
                }
            }]

        def _apply_refund_changes():
            fresh_order = Order.query.get(order.id)
            fresh_payment = Payment.query.get(payment.id)
            if not fresh_order or not fresh_payment:
                raise ValueError('Order or payment not found during refund persistence')
            fresh_order.status = new_order_status
            fresh_order.paid_amount = new_paid_amount
            fresh_payment.status = new_payment_status

            for entry in audit_entries:
                AuditLog.create_log(
                    user_id=entry['user_id'],
                    action=entry['action'],
                    resource_type='Order',
                    resource_id=str(order.id),
                    details=entry['details'],
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent'),
                    commit=False
                )

        _execute_db_operation_with_retry(
            _apply_refund_changes,
            'api.refund_payment.persist'
        )
        
        return jsonify({
            'success': True,
            'message': f'Возврат выполнен на сумму {refund_amount or order.paid_amount} руб.',
            'refund_amount': refund_amount or float(order.paid_amount)
        })
        
    except Exception as e:
        logger.error(f'Refund payment error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка возврата: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
@role_required('ADMIN')
def cancel_order(order_id):
    """Cancel order manually (admin only)"""
    try:
        order = Order.query.get_or_404(order_id)
        
        data = request.get_json()
        cancellation_reason = data.get('reason', 'Отменен администратором')
        
        void_succeeded = False
        authorized_payment_id = None
        if order.payment_intent_id:
            payment = order.payments.filter_by(
                cp_transaction_id=order.payment_intent_id,
                status='authorized'
            ).first()
            if payment:
                cp_api = CloudPaymentsAPI()
                void_result = cp_api.void_payment(order.payment_intent_id)
                if void_result.get('success'):
                    void_succeeded = True
                    authorized_payment_id = payment.id
                    logger.info(f'Payment {order.payment_intent_id} voided for cancelled order {order.id}')

        def _apply_cancellation():
            fresh_order = Order.query.get(order.id)
            if not fresh_order:
                raise ValueError('Order not found during cancellation')
            fresh_order.status = 'cancelled_manual'
            fresh_order.cancellation_reason = cancellation_reason
            if void_succeeded and authorized_payment_id:
                fresh_payment = Payment.query.get(authorized_payment_id)
                if fresh_payment:
                    fresh_payment.status = 'voided'

        _execute_db_operation_with_retry(
            _apply_cancellation,
            'api.cancel_order.persist'
        )
        
        # Log cancellation
        AuditLog.create_log(
            user_id=current_user.id,
            action='ORDER_CANCELLED_MANUAL',
            resource_type='Order',
            resource_id=str(order.id),
            details={
                'cancellation_reason': cancellation_reason,
                'order_status': order.status
            },
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': 'Заказ отменен успешно'
        })
        
    except Exception as e:
        logger.error(f'Cancel order error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка отмены заказа: {str(e)}'}), 500

@bp.route('/payment/create-intent', methods=['POST'])
@login_required
def create_payment_intent():
    """Create payment intent and set order to awaiting_payment"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        payment_method = data.get('payment_method', 'card')
        
        if not order_id:
            return jsonify({'success': False, 'error': 'Order ID required'}), 400
        
        order = Order.query.get_or_404(order_id)
        
        # Check if user has access to this order
        if current_user.role not in ['ADMIN', 'MOM', 'OPERATOR']:
            if order.customer_id != current_user.id:
                return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Check if order is in correct status
        if order.status != 'checkout_initiated':
            return jsonify({'success': False, 'error': 'Order is not in checkout_initiated status'}), 409
        
        # Update order status and set payment expiration
        from datetime import timedelta
        payment_expiration = moscow_now_naive() + timedelta(minutes=15)

        def _mark_order_awaiting_payment():
            fresh_order = Order.query.get(order.id)
            if not fresh_order:
                raise ValueError('Order not found during payment intent creation')
            fresh_order.status = 'awaiting_payment'
            fresh_order.payment_method = payment_method
            fresh_order.payment_expires_at = payment_expiration

        _execute_db_operation_with_retry(
            _mark_order_awaiting_payment,
            'api.create_payment_intent.awaiting_payment'
        )
        
        # Create payment widget data
        cp_api = CloudPaymentsAPI()
        payment_data = cp_api.create_payment_widget_data(order, payment_method)
        
        if not payment_data:
            def _rollback_payment_intent_state():
                fresh_order = Order.query.get(order.id)
                if not fresh_order:
                    return
                fresh_order.status = 'checkout_initiated'
                fresh_order.payment_method = None
                fresh_order.payment_expires_at = None

            _execute_db_operation_with_retry(
                _rollback_payment_intent_state,
                'api.create_payment_intent.rollback'
            )
            return jsonify({'success': False, 'error': 'Failed to create payment intent'}), 500
        
        # Log payment intent creation
        AuditLog.create_log(
            user_id=current_user.id,
            action='PAYMENT_INTENT_CREATED',
            resource_type='Order',
            resource_id=str(order.id),
            details={
                'payment_method': payment_method,
                'expires_at': order.payment_expires_at.isoformat(),
                'amount': float(order.total_amount)
            },
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'payment_data': payment_data,
            'order_id': order.id,
            'expires_at': order.payment_expires_at.isoformat()
        })
        
    except Exception as e:
        logger.error(f'Create payment intent error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка создания платежа: {str(e)}'}), 500

@bp.route('/order/create', methods=['POST'])
def create_order():
    """Create order from cart data"""
    try:
        from flask import session
        from app.models import Athlete, VideoType, User
        
        # Get cart from session
        cart = session.get('cart', {})
        
        if not cart:
            return jsonify({'success': False, 'error': 'Корзина пуста'}), 400
        
        # Get form data
        data = request.get_json()
        contact_email = data.get('contact_email')
        contact_phone = data.get('contact_phone')
        contact_first_name = data.get('contact_first_name', '')
        contact_last_name = data.get('contact_last_name', '')
        comment = data.get('comment', '')
        
        if not contact_email:
            return jsonify({'success': False, 'error': 'Email обязателен для оформления заказа'}), 400
        
        # ✅ ВАЛИДАЦИЯ И НОРМАЛИЗАЦИЯ ТЕЛЕФОНА (ОБЯЗАТЕЛЬНОЕ ПОЛЕ)
        if not contact_phone:
            return jsonify({'success': False, 'error': 'Номер телефона обязателен для оформления заказа'}), 400
        
        from app.utils.validators import normalize_phone
        normalized_phone = normalize_phone(contact_phone)
        
        if not normalized_phone or (not normalized_phone.startswith('+7') or len(normalized_phone.replace('+', '')) != 11):
            return jsonify({
                'success': False, 
                'error': 'Неверный формат номера телефона. Используйте формат: 89060943936, 79060943936, +79060943936 или 9060943936'
            }), 400
        
        contact_phone = normalized_phone
        
        # ✅ ВАЛИДАЦИЯ EMAIL
        try:
            from email_validator import validate_email, EmailNotValidError
            validate_email(contact_email, check_deliverability=False)
        except EmailNotValidError as e:
            return jsonify({'success': False, 'error': f'Неверный формат email: {str(e)}'}), 400
        except ImportError:
            # Если email_validator не установлен, используем простую проверку
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, contact_email):
                return jsonify({'success': False, 'error': 'Неверный формат email'}), 400
        
        # Clean up any existing pending orders from session
        pending_order_id = session.get('pending_order_id')
        if pending_order_id:
            # ✅ Проверка наличия заказа перед удалением
            old_order = Order.query.filter_by(id=pending_order_id).first()
            if old_order and old_order.status == 'checkout_initiated':
                db.session.delete(old_order)
                db.session.commit()
            session.pop('pending_order_id', None)
        
        # Process cart items
        cart_items = []
        total_amount = 0
        video_types = []
        
        for item_id, quantity in cart.items():
            try:
                athlete_id, video_type_id = map(int, item_id.split('_'))
                # ✅ Используем get_or_404 или проверку - в этом случае проверка оправдана
                athlete = Athlete.query.filter_by(id=athlete_id).first()
                video_type = VideoType.query.filter_by(id=video_type_id).first()
                
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
                    return jsonify({'success': False, 'error': f'Товар {item_id} не найден'}), 400
            except (ValueError, AttributeError):
                return jsonify({'success': False, 'error': f'Ошибка в данных товара {item_id}'}), 400
        
        if not cart_items:
            return jsonify({'success': False, 'error': 'Корзина пуста или содержит некорректные товары'}), 400
        
        # Get or create customer user (or use test mode)
        customer_id = None
        if current_user.is_authenticated:
            customer_id = current_user.id
        else:
            # Check if user already exists
            existing_user = User.query.filter_by(email=contact_email).first()
            if existing_user:
                customer_id = existing_user.id
            else:
                # For test mode, create a temporary user or use None
                # This allows testing payments without full user registration
                if current_app.config.get('TEST_MODE', False):
                    # In test mode, we can create orders without users
                    customer_id = None
                else:
                    # Create new user
                    import secrets
                    import string
                    
                    # Generate random password
                    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
                    
                    new_user = User(
                        email=contact_email,
                        full_name=f"{contact_first_name} {contact_last_name}".strip() or 'Клиент',
                        role='CUSTOMER',
                        is_active=True
                    )
                    new_user.set_password(password)
                    db.session.add(new_user)
                    db.session.flush()  # Get the ID
                    customer_id = new_user.id
                    
                    # Send credentials email
                    try:
                        from app.utils.email import send_user_credentials_email
                        send_user_credentials_email(new_user, password)
                    except Exception as e:
                        logger.error(f'Error sending credentials email: {str(e)}')
                    
                    # Auto-login the new user
                    from flask_login import login_user
                    login_user(new_user, remember=False)
        
        # Create order
        order = Order(
            order_number=Order.generate_order_number(),
            generated_order_number=Order.generate_human_order_number(),
            customer_id=customer_id,
            event_id=cart_items[0]['athlete'].category.event_id,
            category_id=cart_items[0]['athlete'].category_id,
            athlete_id=cart_items[0]['athlete'].id,
            video_types=video_types,
            total_amount=total_amount,
            status='checkout_initiated',
            contact_email=contact_email,
            contact_phone=contact_phone,
            contact_first_name=contact_first_name,
            contact_last_name=contact_last_name,
            comment=comment
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
                    logger.warning(f'Database locked in API create_order, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                    db.session.add(order)  # Re-add after rollback
                else:
                    db.session.rollback()
                    logger.error(f'Error creating order via API after {attempt + 1} attempts: {str(e)}')
                    return jsonify({
                        'success': False, 
                        'error': 'База данных временно недоступна. Попробуйте еще раз через несколько секунд.'
                    }), 503
            except Exception as e:
                db.session.rollback()
                logger.error(f'Error creating order via API: {str(e)}', exc_info=True)
                return jsonify({
                    'success': False, 
                    'error': f'Ошибка создания заказа: {str(e)}'
                }), 500
        
        # Store order ID in session
        session['pending_order_id'] = order.id
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'message': 'Заказ создан успешно'
        })
        
    except Exception as e:
        logger.error(f'Create order error: {str(e)}', exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка создания заказа: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/update-comments', methods=['POST'])
@login_required
@role_required('OPERATOR', 'ADMIN', 'MOM')
def update_order_comments(order_id):
    """Update order comments and refund status"""
    try:
        import time
        import random
        from sqlalchemy.exc import OperationalError
        
        order = Order.query.get_or_404(order_id)
        
        data = request.get_json()
        operator_comment = data.get('operator_comment', '')
        partial_refund = data.get('partial_refund', False)
        refund_reason = data.get('refund_reason', '')
        
        # Update order comments
        order.operator_comment = operator_comment
        
        # Update refund status and reason
        old_status = order.status
        if partial_refund:
            order.status = 'refund_required'
            order.refund_reason = refund_reason
        else:
            # ✅ Если снимаем флаг частичного возврата, вернуться к правильному статусу
            if order.status == 'refund_required':
                # ✅ Вернуться к статусу, который был до refund_required
                if order.video_links:
                    order.status = 'links_sent'  # ✅ Ссылки уже были отправлены
                elif order.operator_id:
                    order.status = 'processing'  # ✅ В обработке у оператора
                else:
                    order.status = 'paid'  # ✅ Оплачен, но еще не взят оператором
            order.refund_reason = None
        
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
                    logger.warning(f'Database locked in update_order_comments, retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                    # Re-apply changes after rollback
                    order.operator_comment = operator_comment
                    if partial_refund:
                        order.status = 'refund_required'
                        order.refund_reason = refund_reason
                    else:
                        if order.status == 'refund_required':
                            if order.video_links:
                                order.status = 'links_sent'
                            elif order.operator_id:
                                order.status = 'processing'
                            else:
                                order.status = 'paid'
                        order.refund_reason = None
                else:
                    db.session.rollback()
                    logger.error(f'Error updating order comments after {attempt + 1} attempts: {str(e)}')
                    raise
        
        # Log action
        AuditLog.create_log(
            user_id=current_user.id,
            action='ORDER_COMMENTS_UPDATE',
            resource_type='Order',
            resource_id=str(order.id),
            details={'operator_comment': operator_comment, 'partial_refund': partial_refund, 'refund_reason': refund_reason, 'old_status': old_status, 'new_status': order.status},
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': 'Комментарии обновлены успешно'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Update order comments error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

def _add_status_change_message(order_id, new_status, comment, user_id):
    """Add system message to chat when status changes"""
    try:
        from app.models import OrderChat, ChatMessage
        from app.utils.order_status import get_status_label
        
        # Create or get chat
        chat = OrderChat.query.filter_by(order_id=order_id).first()
        if not chat:
            chat = OrderChat(order_id=order_id)
            db.session.add(chat)
            db.session.commit()
        
        # Create status message
        status_messages = {
            'checkout_initiated': 'Заказ возвращен к оформлению',
            'awaiting_payment': 'Заказ ожидает оплаты клиентом',
            'paid': 'Оплата зафиксирована, заказ ждет оператора',
            'processing': 'Заказ взят в обработку',
            'awaiting_info': 'Требуется дополнительная информация от клиента',
            'links_sent': 'Ссылки на видео отправлены клиенту',
            'completed': 'Заказ завершен',
            'completed_partial_refund': 'Заказ завершен с частичным возвратом',
            'refund_required': 'По заказу требуется возврат',
            'cancelled_unpaid': 'Заказ отменен (не оплачен)',
            'cancelled_manual': 'Заказ отменен вручную',
            'refunded_partial': 'Оформлен частичный возврат',
            'refunded_full': 'Оформлен полный возврат',
        }
        
        message_text = status_messages.get(new_status, f'Статус изменен на {get_status_label(new_status)}')
        if comment:
            message_text += f'. Комментарий: {comment}'
        
        system_message = ChatMessage(
            chat_id=chat.id,
            sender_id=user_id,
            message=message_text,
            message_type='system'
        )
        db.session.add(system_message)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to add system message: {e}")

# Register CloudPayments webhook routes
register_cloudpayments_routes(bp)