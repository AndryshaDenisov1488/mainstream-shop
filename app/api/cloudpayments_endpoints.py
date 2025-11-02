"""
CloudPayments Webhook Endpoints
Handles webhook notifications from CloudPayments
"""

from flask import request, jsonify, current_app
from app import db
from app.models import Order, Payment, User, AuditLog
from app.utils.cloudpayments import CloudPaymentsAPI
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

def register_cloudpayments_routes(bp):
    """Register CloudPayments webhook routes"""
    
    @bp.route('/cloudpayments/webhook', methods=['POST'])
    def cloudpayments_webhook():
        """Handle CloudPayments webhook notifications"""
        try:
            # ВАЖНО: Получаем сырые данные ДО любого парсинга
            # request.get_data() получает сырые байты, затем декодируем как текст
            raw_data_bytes = request.get_data(cache=False)
            raw_data = raw_data_bytes.decode('utf-8')
            
            # Альтернативный способ - получить из WSGI environ
            # raw_data_alt = request.environ.get('wsgi.input').read() если нужно
            
            # CloudPayments может отправлять подпись в разных заголовках
            # Приоритет: Content-Hmac (основной), затем X-Content-Hmac
            signature = (
                request.headers.get('Content-Hmac') or
                request.headers.get('X-Content-Hmac') or
                request.headers.get('Content-HMAC') or
                request.headers.get('X-Content-HMAC') or
                request.headers.get('X-Content-Signature') or
                request.headers.get('Content-Signature')
            )
            
            # Детальное логирование для отладки
            logger.info(f'=== WEBHOOK DEBUG START ===')
            logger.info(f'Content-Type: {request.headers.get("Content-Type")}')
            logger.info(f'Content-Length: {request.headers.get("Content-Length")}')
            logger.info(f'Raw data length: {len(raw_data)} bytes')
            logger.info(f'Raw data (first 200 chars): {raw_data[:200]}')
            logger.info(f'Signature header (Content-Hmac): {request.headers.get("Content-Hmac")}')
            logger.info(f'Signature header (X-Content-Hmac): {request.headers.get("X-Content-Hmac")}')
            logger.info(f'Using signature: {signature[:40] if signature else "None"}...')
            logger.info(f'All headers: {dict(request.headers)}')
            
            # Verify signature
            cp_api = CloudPaymentsAPI()
            signature_valid = cp_api.verify_webhook_signature(raw_data, signature)
            
            logger.info(f'Signature verification result: {signature_valid}')
            logger.info(f'=== WEBHOOK DEBUG END ===')
            
            if not signature_valid:
                logger.warning(f'Invalid webhook signature. Raw data: {raw_data[:500]}')
                # В тестовом режиме можем пропустить проверку подписи временно
                test_mode = current_app.config.get('CLOUDPAYMENTS_TEST_MODE', False)
                if not test_mode:
                    logger.error('REJECTING webhook due to invalid signature (not in test mode)')
                    return jsonify({'code': 13, 'message': 'Invalid signature'}), 200
                else:
                    logger.warning('TEST MODE: Bypassing signature verification - proceeding anyway')
            
            # Parse webhook data - CloudPayments отправляет form-urlencoded
            logger.info(f'=== PARSING WEBHOOK DATA ===')
            logger.info(f'Content-Type: {request.content_type}')
            logger.info(f'request.form: {dict(request.form)}')
            logger.info(f'request.form keys: {list(request.form.keys())}')
            
            if request.content_type and 'application/x-www-form-urlencoded' in request.content_type:
                # Парсим form-urlencoded данные
                from urllib.parse import unquote
                webhook_data = {}
                for key, value in request.form.items():
                    # CloudPayments может отправлять некоторые значения закодированными
                    decoded_value = unquote(value) if value else value
                    webhook_data[key] = decoded_value
                    logger.info(f'Parsed: {key} = {decoded_value}')
                
                # Также попробуем парсить напрямую из raw_data если form пустой
                if not webhook_data:
                    logger.warning('request.form is empty, trying to parse from raw_data')
                    from urllib.parse import parse_qs
                    parsed_qs = parse_qs(raw_data)
                    for key, values in parsed_qs.items():
                        webhook_data[key] = unquote(values[0]) if values and values[0] else ''
                        logger.info(f'Parsed from raw_data: {key} = {webhook_data[key]}')
            else:
                # Fallback на JSON если формат другой
                webhook_data = request.get_json() or {}
                logger.info(f'Parsed as JSON: {webhook_data}')
            
            logger.info(f'Final webhook_data: {webhook_data}')
            
            # CloudPayments использует OperationType вместо NotificationType
            # Также проверяем Status для определения типа уведомления
            operation_type = webhook_data.get('OperationType')
            status = webhook_data.get('Status')
            notification_type = webhook_data.get('NotificationType')  # Для обратной совместимости
            
            logger.info(f'OperationType: {operation_type}, Status: {status}, NotificationType: {notification_type}')
            
            # Определяем тип уведомления
            if notification_type:
                # Используем NotificationType если есть (старый формат)
                notification_type_to_handle = notification_type
            elif operation_type == 'Payment':
                # Payment операция - может быть Check, Pay, Confirm
                if status == 'Completed':
                    notification_type_to_handle = 'Pay'  # Успешный платеж
                elif status == 'Authorized':
                    notification_type_to_handle = 'Pay'  # Авторизован (двухстадийный)
                else:
                    notification_type_to_handle = 'Check'  # Проверка перед оплатой
            elif operation_type == 'PaymentFailed':
                notification_type_to_handle = 'Fail'
            elif operation_type == 'Refund':
                notification_type_to_handle = 'Refund'
            elif operation_type == 'Cancel':
                notification_type_to_handle = 'Cancel'
            else:
                logger.error(f'⚠️ Unknown OperationType: {operation_type}, Status: {status}')
                logger.error(f'Webhook data: {webhook_data}')
                notification_type_to_handle = None
            
            logger.info(f'Determined notification type: {notification_type_to_handle}')
            logger.info(f'Full webhook data: {webhook_data}')
            
            # Handle different notification types
            if notification_type_to_handle == 'Check':
                return handle_check_notification(webhook_data)
            elif notification_type_to_handle == 'Pay':
                return handle_pay_notification(webhook_data)
            elif notification_type_to_handle == 'Fail':
                return handle_fail_notification(webhook_data)
            elif notification_type_to_handle == 'Confirm':
                return handle_confirm_notification(webhook_data)
            elif notification_type_to_handle == 'Refund':
                return handle_refund_notification(webhook_data)
            elif notification_type_to_handle == 'Cancel':
                return handle_cancel_notification(webhook_data)
            else:
                logger.warning(f'Unknown notification type: {notification_type_to_handle}')
                logger.warning(f'OperationType: {operation_type}, Status: {status}')
                return jsonify({'code': 13, 'message': 'Unknown notification type'}), 200
                
        except Exception as e:
            logger.error(f'Webhook error: {str(e)}')
            return jsonify({'code': 13, 'message': 'Internal server error'}), 200
    
def handle_check_notification(data):
    """Handle CloudPayments Check notification (before payment)"""
    try:
        # Extract order information
        invoice_id = data.get('InvoiceId')
        amount = data.get('Amount')
        currency = data.get('Currency')
        
        # Validate order exists and amount matches
        order = Order.query.filter_by(order_number=invoice_id).first()
        if not order:
            logger.warning(f'Order not found: {invoice_id}')
            return jsonify({'code': 10, 'message': 'Order not found'}), 200
        
        if float(amount) != float(order.total_amount):
            logger.warning(f'Amount mismatch: {amount} vs {order.total_amount}')
            return jsonify({'code': 11, 'message': 'Amount mismatch'}), 200
        
        # Check if order is already paid
        existing_payment = Payment.query.filter_by(
            order_id=order.id,
            status='authorized'
        ).first()
        
        if existing_payment:
            logger.warning(f'Order already has authorized payment: {invoice_id}')
            return jsonify({'code': 12, 'message': 'Order already paid'}), 200
        
        # All checks passed
        return jsonify({'code': 0, 'message': 'OK'}), 200
        
    except Exception as e:
        logger.error(f'Check notification error: {str(e)}')
        return jsonify({'code': 13, 'message': 'Internal error'}), 200

def handle_pay_notification(data):
    """Handle CloudPayments Pay notification (after successful payment)"""
    try:
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError
        
        # Extract payment information
        # CloudPayments может использовать разные поля в зависимости от формата
        transaction_id = data.get('TransactionId')
        invoice_id = data.get('InvoiceId')
        amount = data.get('Amount') or data.get('PaymentAmount')  # PaymentAmount - новый формат
        currency = data.get('Currency') or data.get('PaymentCurrency')  # PaymentCurrency - новый формат
        card_mask = data.get('CardMask') or (data.get('CardFirstSix', '') + '****' + data.get('CardLastFour', ''))
        email = data.get('Email')
        status = data.get('Status')  # Completed, Authorized и т.д.
        
        logger.info(f'Processing Pay notification: transaction_id={transaction_id}, invoice_id={invoice_id}, amount={amount}, status={status}')
        
        # ✅ ИДЕМПОТЕНТНОСТЬ С БЛОКИРОВКОЙ для защиты от race condition
        try:
            with db.session.begin():
                # Блокируем проверку существования платежа
                stmt = select(Payment).where(
                    Payment.cp_transaction_id == transaction_id
                ).with_for_update()
                
                existing_payment = db.session.scalar(stmt)
                
                if existing_payment:
                    logger.info(f'Payment {transaction_id} already processed, skipping')
                    return jsonify({'code': 0, 'message': 'Already processed'}), 200
                
                # Find order in database
                order = Order.query.filter_by(order_number=invoice_id).first()
                if not order:
                    logger.error(f'Order not found for payment: {invoice_id}')
                    return jsonify({'code': 10, 'message': 'Order not found'}), 200
                
                # Check if order is in correct status and not expired
                if order.status not in ['awaiting_payment', 'checkout_initiated']:
                    logger.error(f'Order {invoice_id} is not in awaiting_payment status: {order.status}')
                    return jsonify({'code': 12, 'message': 'Order already processed'}), 200
                
                # Check if payment has expired
                if order.payment_expires_at and datetime.utcnow() > order.payment_expires_at:
                    logger.error(f'Payment for order {invoice_id} has expired')
                    return jsonify({'code': 12, 'message': 'Payment expired'}), 200
                
                # Determine payment method
                payment_method = 'card'
                if 'sbp' in data.get('PaymentMethod', '').lower():
                    payment_method = 'sbp'
                
                # Определяем статус платежа в зависимости от Status от CloudPayments
                # Status может быть: Completed, Authorized, и т.д.
                if status == 'Completed':
                    payment_status = 'confirmed'  # Платеж сразу подтвержден (одностадийный)
                    order_status = 'paid'
                elif status == 'Authorized':
                    payment_status = 'authorized'  # Платеж авторизован, нужна подтверждение (двухстадийный)
                    order_status = 'paid'
                else:
                    payment_status = 'authorized'  # По умолчанию авторизован
                    order_status = 'paid'
                
                # Create payment record
                payment = Payment(
                    order_id=order.id,
                    cp_transaction_id=transaction_id,
                    amount=float(amount) if amount else 0.0,
                    currency=currency or 'RUB',
                    status=payment_status,
                    method=payment_method,
                    card_mask=card_mask,
                    email=email,
                    raw_payload=data
                )
                
                db.session.add(payment)
                
                # Update order status
                order.status = order_status
                order.paid_amount = float(amount) if amount else order.total_amount
                order.payment_intent_id = transaction_id
                order.payment_method = payment_method
                
                logger.info(f'Payment created: id={payment.id}, status={payment_status}, order_status={order_status}')
                
                # Коммит произойдет автоматически при выходе из with db.session.begin()
                
        except IntegrityError:
            # Если произошла ошибка уникальности (двойной webhook)
            logger.warning(f'Duplicate payment {transaction_id} detected (IntegrityError)')
            return jsonify({'code': 0, 'message': 'Already processed'}), 200
        
        # Логирование после успешного коммита
        AuditLog.create_log(
            user_id=None,  # System action
            action='PAYMENT_AUTHORIZED',
            resource_type='Order',
            resource_id=str(order.id),
            details={
                'transaction_id': transaction_id,
                'amount': float(amount),
                'currency': currency,
                'card_mask': card_mask,
                'payment_method': payment_method
            },
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            commit=True  # ✅ Коммитим отдельно, т.к. основная транзакция уже завершена
        )
        
        # Send payment success email to customer
        try:
            from app.utils.email import send_payment_success_email
            send_payment_success_email(order)
            logger.info(f'Payment success email sent for order {order.generated_order_number}')
        except Exception as e:
            logger.error(f'Failed to send payment success email: {e}')
        
        logger.info(f'Payment authorized for order {order.generated_order_number}, transaction {transaction_id}')
        return jsonify({'code': 0, 'message': 'OK'}), 200
        
    except Exception as e:
        logger.error(f'Pay notification error: {str(e)}')
        db.session.rollback()
        return jsonify({'code': 13, 'message': 'Internal error'}), 200

def handle_fail_notification(data):
    """Handle CloudPayments Fail notification (payment failed)"""
    try:
        # Extract information
        transaction_id = data.get('TransactionId')
        invoice_id = data.get('InvoiceId')
        reason = data.get('Reason')
        
        # Find order
        order = Order.query.filter_by(order_number=invoice_id).first()
        if order:
            # Log failed payment attempt
            AuditLog.create_log(
                user_id=None,
                action='PAYMENT_FAILED',
                resource_type='Order',
                resource_id=str(order.id),
                details={
                    'transaction_id': transaction_id,
                    'reason': reason,
                    'invoice_id': invoice_id
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        
        logger.info(f'Payment failed for transaction {transaction_id}, reason: {reason}')
        return jsonify({'code': 0, 'message': 'OK'}), 200
        
    except Exception as e:
        logger.error(f'Fail notification error: {str(e)}')
        return jsonify({'code': 13, 'message': 'Internal error'}), 200

def handle_confirm_notification(data):
    """Handle CloudPayments Confirm notification (payment confirmed)"""
    try:
        transaction_id = data.get('TransactionId')
        amount = data.get('Amount')
        
        # Find payment and update status
        payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
        if payment:
            # Idempotency check
            if payment.status == 'confirmed':
                logger.info(f'Payment {transaction_id} already confirmed, skipping')
                return jsonify({'code': 0, 'message': 'Already confirmed'}), 200
            
            payment.status = 'confirmed'
            payment.mom_confirmed = True
            payment.confirmed_at = datetime.utcnow()
            
            # Update order paid_amount if partial capture
            if amount and float(amount) != float(payment.amount):
                payment.order.paid_amount = amount
                payment.order.status = 'completed'
            
            db.session.commit()
            
            # Log confirmation
            AuditLog.create_log(
                user_id=None,
                action='PAYMENT_CONFIRMED',
                resource_type='Payment',
                resource_id=str(payment.id),
                details={
                    'transaction_id': transaction_id,
                    'amount': float(amount) if amount else float(payment.amount),
                    'order_id': payment.order.id
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            logger.info(f'Payment {transaction_id} confirmed for amount {amount}')
        else:
            logger.warning(f'Payment {transaction_id} not found for confirmation')
        
        return jsonify({'code': 0, 'message': 'OK'}), 200
        
    except Exception as e:
        logger.error(f'Confirm notification error: {str(e)}')
        return jsonify({'code': 13, 'message': 'Internal error'}), 200

def handle_refund_notification(data):
    """Handle CloudPayments Refund notification"""
    try:
        transaction_id = data.get('TransactionId')
        amount = data.get('Amount')
        
        # Find payment and update status
        payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
        if payment:
            if amount and float(amount) < float(payment.amount):
                payment.status = 'refunded_partial'
            else:
                payment.status = 'refunded_full'
            db.session.commit()
            
            logger.info(f'Payment {transaction_id} refunded for amount {amount}')
        
        return jsonify({'code': 0, 'message': 'OK'}), 200
        
    except Exception as e:
        logger.error(f'Refund notification error: {str(e)}')
        return jsonify({'code': 13, 'message': 'Internal error'}), 200

def handle_cancel_notification(data):
    """Handle CloudPayments Cancel notification"""
    try:
        transaction_id = data.get('TransactionId')
        
        # Find payment and update status
        payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
        if payment:
            payment.status = 'voided'
            payment.order.status = 'cancelled_unpaid'
            db.session.commit()
            
            logger.info(f'Payment {transaction_id} cancelled')
        
        return jsonify({'code': 0, 'message': 'OK'}), 200
        
    except Exception as e:
        logger.error(f'Cancel notification error: {str(e)}')
        return jsonify({'code': 13, 'message': 'Internal error'}), 200
