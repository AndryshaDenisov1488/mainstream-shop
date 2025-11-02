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
import json
import logging
import base64
import requests

logger = logging.getLogger(__name__)

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
        
        # Update order status to awaiting payment
        order.status = 'awaiting_payment'
        order.payment_method = payment_method
        
        db.session.commit()
        
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
                
                # Create payment record
                payment = Payment(
                    order_id=order.id,
                    cp_transaction_id=transaction_id,
                    amount=amount,
                    currency=currency,
                    status='authorized',
                    method=payment_method,
                    email=email,
                    raw_payload=result
                )
                
                db.session.add(payment)
                
                # Update order status
                order.status = 'paid'
                order.paid_amount = amount
                order.payment_intent_id = transaction_id
                order.payment_method = payment_method
                
                db.session.commit()
                
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
        
        # Update order
        order.status = new_status
        if operator_comment:
            order.operator_comment = operator_comment
        
        if new_status in ['completed', 'completed_partial_refund', 'cancelled_unpaid', 'cancelled_manual', 'refunded_full', 'refunded_partial']:
            order.processed_at = db.func.now()
        
        # Если заказ отменяется, сохраняем причину и отправляем email
        if new_status in ['cancelled_unpaid', 'cancelled_manual']:
            order.cancellation_reason = operator_comment
            # Отправляем email клиенту
            try:
                from app.utils.email import send_order_cancellation_email
                send_order_cancellation_email(order, operator_comment)
            except Exception as e:
                print(f"Error sending cancellation email: {e}")
        
        db.session.commit()
        
        # Log action
        AuditLog.create_log(
            user_id=current_user.id,
            action='ORDER_STATUS_CHANGE',
            resource_type='Order',
            resource_id=str(order.id),
            details={'old_status': order.status, 'new_status': new_status, 'comment': operator_comment},
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
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/order/<int:order_id>/operator-change-status', methods=['POST'])
@login_required
@role_required('OPERATOR')
def operator_change_order_status(order_id):
    """Change order status by operator"""
    try:
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
        
        # Update order
        order.status = new_status
        if operator_comment:
            order.operator_comment = operator_comment
        
        # Set operator if not set
        if not order.operator_id:
            order.operator_id = current_user.id
        
        if new_status in ['completed', 'completed_partial_refund', 'cancelled_unpaid', 'cancelled_manual', 'refunded_full', 'refunded_partial']:
            order.processed_at = db.func.now()
        
        # Если заказ отменяется, сохраняем причину и отправляем email
        if new_status in ['cancelled_unpaid', 'cancelled_manual']:
            order.cancellation_reason = operator_comment
            # Отправляем email клиенту
            try:
                from app.utils.email import send_order_cancellation_email
                send_order_cancellation_email(order, operator_comment)
            except Exception as e:
                print(f"Error sending cancellation email: {e}")
        
        db.session.commit()
        
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
            details={'old_status': order.status, 'new_status': new_status, 'comment': operator_comment},
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
            for key, value in request.form.items():
                if key.startswith('video_link_') and value.strip():
                    video_type_id = key.replace('video_link_', '')
                    video_links[video_type_id] = value.strip()
        
        if not video_links:
            return jsonify({'success': False, 'error': 'Необходимо указать хотя бы одну ссылку на видео'}), 400
        
        # Update order with video links and customer info
        order.video_links = video_links
        order.contact_email = customer_email
        
        # Parse customer name if provided
        if customer_name:
            name_parts = customer_name.strip().split(' ')
            if len(name_parts) >= 2:
                order.contact_last_name = name_parts[0]
                order.contact_first_name = ' '.join(name_parts[1:])
            elif len(name_parts) == 1:
                order.contact_first_name = name_parts[0]
        
        # Set status based on refund requirement
        if partial_refund:
            order.status = 'refund_required'
            if refund_comment:
                order.refund_reason = refund_comment
        else:
            order.status = 'links_sent'
        
        # Save operator comment if provided (separate from refund reason)
        if message:
            order.operator_comment = message
        
        
        order.processed_at = db.func.now()
        
        # If no operator assigned, assign current operator
        if not order.operator_id:
            order.operator_id = current_user.id
        
        db.session.commit()
        
        # Send email with links
        try:
            from app.utils.email import send_video_links_email
            send_video_links_email(order)
        except Exception as e:
            logger.error(f'Failed to send email: {e}')
            # Don't fail the whole operation if email fails
        
        # Log action
        AuditLog.create_log(
            user_id=current_user.id,
            action='ORDER_COMPLETE',
            resource_type='Order',
            resource_id=str(order.id),
            details={'video_links': video_links, 'message': message},
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
        from sqlalchemy.orm import with_for_update
        from sqlalchemy.exc import OperationalError
        
        # Check if user has permission (admin, mom, or operator)
        if not (current_user.role == 'ADMIN' or current_user.role == 'MOM' or current_user.role == 'OPERATOR'):
            return jsonify({'success': False, 'error': 'Недостаточно прав'}), 403
        
        # ✅ ИСПОЛЬЗУЕМ SELECT FOR UPDATE для блокировки строки
        try:
            with db.session.begin():
                # Блокируем строку заказа для обновления (защита от race condition)
                stmt = select(Order).where(
                    Order.id == order_id,
                    Order.status == 'paid',
                    Order.operator_id.is_(None)  # ✅ Проверяем, что оператор еще не назначен
                ).with_for_update()
                
                order = db.session.scalar(stmt)
                
                if not order:
                    return jsonify({
                        'success': False, 
                        'error': 'Заказ недоступен (уже взят другим оператором или не оплачен)'
                    }), 409
                
                # Проверка прав уже сделана выше
                # Назначаем оператора
                order.operator_id = current_user.id
                order.status = 'processing'
                order.processed_at = db.func.now()
                
                # Коммит произойдет автоматически при выходе из with db.session.begin()
                
        except OperationalError as e:
            # Если произошла ошибка блокировки (редко, но возможно)
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
        
        # ✅ Проверка: сумма не может превышать авторизованную сумму платежа
        authorized_payment = order.payments.filter_by(status='authorized').first()
        if not authorized_payment:
            return jsonify({'success': False, 'error': 'Авторизованный платеж не найден'}), 404
        
        if capture_amount > float(authorized_payment.amount):
            return jsonify({
                'success': False, 
                'error': f'Сумма захвата ({capture_amount}) не может превышать авторизованную сумму ({authorized_payment.amount})'
            }), 400
        
        if capture_amount > float(order.total_amount):
            return jsonify({
                'success': False, 
                'error': f'Сумма захвата ({capture_amount}) не может превышать сумму заказа ({order.total_amount})'
            }), 400
        
        payment = authorized_payment
        
        cp_api = CloudPaymentsAPI()
        
        if order.payment_method == 'card':
            # Determine if this is partial or full capture
            is_partial_capture = capture_amount < float(order.total_amount)
            
            if is_partial_capture:
                # ✅ ЧАСТИЧНЫЙ ЗАХВАТ
                confirm_result = cp_api.confirm_payment(payment.cp_transaction_id, capture_amount)
                if not confirm_result.get('success'):
                    return jsonify({'success': False, 'error': f'Ошибка подтверждения платежа: {confirm_result.get("error")}'}), 500
                
                order.paid_amount = capture_amount
                order.status = 'completed_partial_refund'  # ✅ Всегда частичный возврат при частичном захвате
                
                # Log partial capture
                AuditLog.create_log(
                    user_id=current_user.id,
                    action='MOM_CAPTURED_PARTIAL',
                    resource_type='Order',
                    resource_id=str(order.id),
                    details={
                        'captured_amount': capture_amount,
                        'total_amount': float(order.total_amount),
                        'transaction_id': payment.cp_transaction_id
                    },
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent'),
                    commit=False  # ✅ Коммитим вместе с основными изменениями
                )
            else:
                # ✅ ПОЛНЫЙ ЗАХВАТ
                confirm_result = cp_api.confirm_payment(payment.cp_transaction_id)  # Без amount = полный
                if not confirm_result.get('success'):
                    return jsonify({'success': False, 'error': f'Ошибка подтверждения платежа: {confirm_result.get("error")}'}), 500
                
                order.paid_amount = capture_amount
                order.status = 'completed'  # ✅ Полный захват
                
                # Log full capture
                AuditLog.create_log(
                    user_id=current_user.id,
                    action='MOM_CAPTURED_FULL',
                    resource_type='Order',
                    resource_id=str(order.id),
                    details={
                        'captured_amount': capture_amount,
                        'transaction_id': payment.cp_transaction_id
                    },
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent'),
                    commit=False  # ✅ Коммитим вместе с основными изменениями
                )
        else:
            # For SBP, payments are already confirmed, just update status
            order.paid_amount = capture_amount
            if capture_amount < float(order.total_amount):
                order.status = 'completed_partial_refund'
            else:
                order.status = 'completed'
            
            # Log SBP capture
            AuditLog.create_log(
                user_id=current_user.id,
                action='MOM_CAPTURED_SBP',
                resource_type='Order',
                resource_id=str(order.id),
                details={
                    'captured_amount': capture_amount,
                    'payment_method': 'sbp'
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        
        # Update payment status
        payment.status = 'confirmed'
        payment.mom_confirmed = True
        payment.confirmed_at = db.func.now()
        payment.confirmed_by = current_user.id
        
        db.session.commit()  # ✅ Коммитим все вместе: order, payment, audit_log
        
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
        is_full_refund = refund_amount >= float(order.paid_amount)
        
        if is_full_refund:
            # ✅ ПОЛНЫЙ ВОЗВРАТ - заказ отменяется
            order.status = 'refunded_full'
            payment.status = 'refunded_full'
            order.paid_amount = 0
            
            AuditLog.create_log(
                user_id=current_user.id,
                action='MOM_REFUNDED_FULL',
                resource_type='Order',
                resource_id=str(order.id),
                details={
                    'refund_amount': float(order.paid_amount) if order.paid_amount else refund_amount,
                    'transaction_id': payment.cp_transaction_id
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                commit=False  # ✅ Коммитим вместе с изменениями
            )
        else:
            # ✅ ЧАСТИЧНЫЙ ВОЗВРАТ - заказ завершается с частичным возвратом
            order.status = 'completed_partial_refund'  # ✅ ПРАВИЛЬНЫЙ СТАТУС
            payment.status = 'refunded_partial'
            order.paid_amount = float(order.paid_amount) - refund_amount  # ✅ Обновляем сумму
        
            AuditLog.create_log(
                user_id=current_user.id,
                action='MOM_REFUNDED_PARTIAL',
                resource_type='Order',
                resource_id=str(order.id),
                details={
                    'refund_amount': refund_amount,
                    'remaining_amount': float(order.paid_amount),
                    'transaction_id': payment.cp_transaction_id
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                commit=False  # ✅ Коммитим вместе с изменениями
            )
        
        db.session.commit()  # ✅ Коммитим все вместе
        
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
        
        # Update order status
        order.status = 'cancelled_manual'
        order.cancellation_reason = cancellation_reason
        
        # Try to void payment if it exists and is authorized
        if order.payment_intent_id:
            payment = order.payments.filter_by(
                cp_transaction_id=order.payment_intent_id,
                status='authorized'
            ).first()
            
            if payment:
                cp_api = CloudPaymentsAPI()
                void_result = cp_api.void_payment(order.payment_intent_id)
                if void_result.get('success'):
                    payment.status = 'voided'
                    logger.info(f'Payment {order.payment_intent_id} voided for cancelled order {order.id}')
        
        db.session.commit()
        
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
        from datetime import datetime, timedelta
        order.status = 'awaiting_payment'
        order.payment_method = payment_method
        order.payment_expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        db.session.commit()
        
        # Create payment widget data
        cp_api = CloudPaymentsAPI()
        payment_data = cp_api.create_payment_widget_data(order, payment_method)
        
        if not payment_data:
            # Rollback order status
            order.status = 'checkout_initiated'
            order.payment_method = None
            order.payment_expires_at = None
            db.session.commit()
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
        db.session.commit()
        
        # Store order ID in session
        session['pending_order_id'] = order.id
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'message': 'Заказ создан успешно'
        })
        
    except Exception as e:
        logger.error(f'Create order error: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Ошибка создания заказа: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/update-comments', methods=['POST'])
@login_required
@role_required('OPERATOR', 'ADMIN', 'MOM')
def update_order_comments(order_id):
    """Update order comments and refund status"""
    try:
        order = Order.query.get_or_404(order_id)
        
        data = request.get_json()
        operator_comment = data.get('operator_comment', '')
        partial_refund = data.get('partial_refund', False)
        refund_reason = data.get('refund_reason', '')
        
        # Update order comments
        order.operator_comment = operator_comment
        
        # Update refund status and reason
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
        
        db.session.commit()
        
        # Log action
        AuditLog.create_log(
            user_id=current_user.id,
            action='ORDER_COMMENTS_UPDATE',
            resource_type='Order',
            resource_id=str(order.id),
            details={'operator_comment': operator_comment, 'partial_refund': partial_refund, 'refund_reason': refund_reason},
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': 'Комментарии обновлены успешно'
        })
        
    except Exception as e:
        logger.error(f'Update order comments error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

def _add_status_change_message(order_id, new_status, comment, user_id):
    """Add system message to chat when status changes"""
    try:
        from app.models import OrderChat, ChatMessage
        
        # Create or get chat
        chat = OrderChat.query.filter_by(order_id=order_id).first()
        if not chat:
            chat = OrderChat(order_id=order_id)
            db.session.add(chat)
            db.session.commit()
        
        # Create status message
        status_messages = {
            'pending': 'Заказ возвращен в ожидание',
            'processing': 'Заказ взят в обработку',
            'awaiting_info': 'Требуется дополнительная информация от клиента',
            'links_sent': 'Ссылки на видео отправлены клиенту',
            'completed': 'Заказ завершен',
            'completed_partial_refund': 'Заказ завершен с частичным возвратом',
            'refund_required': 'Требуется возврат',
            'cancelled': 'Заказ отменен'
        }
        
        message_text = status_messages.get(new_status, f'Статус изменен на {new_status}')
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
        print(f"Failed to add system message: {e}")

# Register CloudPayments webhook routes
register_cloudpayments_routes(bp)