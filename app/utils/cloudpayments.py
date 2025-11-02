"""
Real CloudPayments Integration
Working with actual CloudPayments API
"""

import hmac
import hashlib
import json
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from flask import current_app, request
from app.models import Order, Payment, User
from app import db
import logging

# Optional cloudpayments import
try:
    import cloudpayments
    CLOUDPAYMENTS_AVAILABLE = True
except ImportError:
    CLOUDPAYMENTS_AVAILABLE = False
    cloudpayments = None

logger = logging.getLogger(__name__)

class CloudPaymentsAPI:
    """Real CloudPayments API integration"""
    
    def __init__(self):
        if not CLOUDPAYMENTS_AVAILABLE:
            logger.warning("CloudPayments library not available")
        
        # ✅ Используем config вместо хардкода
        from flask import current_app
        self.public_id = current_app.config.get('CLOUDPAYMENTS_PUBLIC_ID')
        self.api_secret = current_app.config.get('CLOUDPAYMENTS_API_SECRET')
        self.currency = current_app.config.get('CLOUDPAYMENTS_CURRENCY', 'RUB')
        self.test_mode = current_app.config.get('CLOUDPAYMENTS_TEST_MODE', False)
        self.base_url = 'https://api.cloudpayments.ru'
        
        # Проверка наличия ключей - в dev режиме не бросаем ошибку, только предупреждение
        if not self.public_id or not self.api_secret:
            is_production = os.environ.get('FLASK_ENV') == 'production'
            if is_production:
                logger.error("CloudPayments credentials not configured!")
                raise ValueError("CloudPayments credentials not configured. Set CLOUDPAYMENTS_PUBLIC_ID and CLOUDPAYMENTS_API_SECRET")
            else:
                logger.warning("⚠️ CloudPayments credentials not configured! Payment functionality will not work.")
                logger.warning("⚠️ To enable payments, set CLOUDPAYMENTS_PUBLIC_ID and CLOUDPAYMENTS_API_SECRET in .env")
                # В dev режиме не бросаем ошибку, просто ставим None
                # Это позволит приложению работать, но платежи не будут доступны
        
        # Log configuration for debugging (БЕЗ СЕКРЕТОВ)
        logger.info(f"CloudPayments API initialized:")
        logger.info(f"  Public ID: {self.public_id[:10]}..." if self.public_id else "  Public ID: None")
        logger.info(f"  API Secret: {'*' * 20}")
        logger.info(f"  Currency: {self.currency}")
        logger.info(f"  Test Mode: {self.test_mode}")
        logger.info(f"  Base URL: {self.base_url}")
    

    def create_payment_widget_data(self, order: Order, payment_method: str = 'card') -> dict:
        """
        Create CloudPayments payment widget data for JavaScript initialization
        
        Args:
            order: Order object
            payment_method: 'card' or 'sbp' for System of Fast Payments
            
        Returns:
            Dictionary with payment data for JavaScript widget
        """
        if not CLOUDPAYMENTS_AVAILABLE:
            logger.error("CloudPayments library not available - check if cloudpayments package is installed")
            return {}
        
        try:
            # Check if CloudPayments is properly configured
            if not self.public_id or not self.api_secret:
                error_msg = "CloudPayments не настроен. Установите CLOUDPAYMENTS_PUBLIC_ID и CLOUDPAYMENTS_API_SECRET в .env файле"
                logger.error(f"CloudPayments not properly configured - missing public_id or api_secret")
                logger.error(f"  public_id: {self.public_id}")
                logger.error(f"  api_secret: {'present' if self.api_secret else 'missing'}")
                raise ValueError(error_msg)
            
            # Prepare payment data for widget according to CloudPayments documentation
            # Используем order_number вместо generated_order_number для совместимости
            order_number = getattr(order, 'generated_order_number', None) or order.order_number
            
            payment_data = {
                'publicId': self.public_id,
                'description': f'Заказ видео {order_number}',
                'amount': float(order.total_amount),  # CloudPayments ожидает сумму в рублях, не в копейках
                'currency': self.currency,
                'invoiceId': order.order_number,
                'email': order.contact_email,
                'accountId': str(order.customer_id) if order.customer_id else order.contact_email  # Customer ID or email for account identification
            }
            
            # Add payment method specific parameters
            if payment_method == 'sbp':
                payment_data['paymentMethod'] = 'sbp'
                payment_data['description'] = f'СБП: Заказ видео {order_number}'
            
            logger.info(f'Payment widget data created for order {order.order_number}, method: {payment_method}')
            logger.info(f'Payment data details: publicId={self.public_id}, amount={payment_data["amount"]}, currency={payment_data["currency"]}, invoiceId={payment_data["invoiceId"]}, email={payment_data["email"]}')
            logger.info(f'Full payment data: {payment_data}')
            
            return payment_data
            
        except Exception as e:
            logger.error(f'Error creating payment widget data for order {order.order_number}: {str(e)}')
            raise
    
    def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process CloudPayments webhook
        
        Args:
            webhook_data: Webhook payload
            
        Returns:
            Processing result
        """
        try:
            # Handle 'check' notification - CloudPayments sends this before processing payment
            if webhook_data.get('NotificationType') == 'Check':
                logger.info(f'Received check notification for transaction {webhook_data.get("TransactionId")}')
                return {
                    'success': True,
                    'code': 0,  # CloudPayments expects code: 0 for successful check
                    'message': 'Check notification processed'
                }
            
            transaction_id = webhook_data.get('TransactionId')
            status = webhook_data.get('Status')
            
            if not transaction_id or not status:
                return {
                    'success': False,
                    'error': 'Missing required fields in webhook'
                }
            
            # Find payment by invoice ID or transaction ID
            order_number = webhook_data.get('InvoiceId')
            if order_number:
                order = Order.query.filter_by(order_number=order_number).first()
                if order:
                    payment = Payment.query.filter_by(order_id=order.id).first()
                else:
                    payment = None
            else:
                payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
            
            if not payment:
                # Create payment record if it doesn't exist (first webhook call)
                if order:
                    payment = Payment(
                        order_id=order.id,
                        cp_transaction_id=transaction_id,
                        amount=webhook_data.get('Amount', 0),
                        currency=webhook_data.get('Currency', 'RUB'),
                        status='authorized',
                        email=webhook_data.get('Email', order.contact_email),
                        method='card'  # Default, will be updated if available
                    )
                    db.session.add(payment)
                    logger.info(f'Created payment record for order {order.order_number}')
                else:
                    logger.warning(f'Order not found for transaction {transaction_id}')
                    return {
                        'success': False,
                        'error': 'Order not found'
                    }
            
            # Update payment status based on webhook
            if status == 'Authorized':
                payment.status = 'authorized'
                if not payment.cp_transaction_id:  # Only set if not already set
                    payment.cp_transaction_id = transaction_id
                payment.order.status = 'paid'
                
                # Send confirmation email
                from app.utils.email import send_order_confirmation_email
                send_order_confirmation_email(payment.order)
                
            elif status == 'Completed':
                payment.status = 'confirmed'
                payment.mom_confirmed = True
                payment.confirmed_at = datetime.utcnow()
                
            elif status == 'Voided':
                payment.status = 'voided'
                payment.order.status = 'cancelled_unpaid'
                
                # Send cancellation email
                from app.utils.email import send_order_cancellation_email
                send_order_cancellation_email(payment.order)
                
            elif status == 'Refunded':
                payment.status = 'refunded_full'
            
            else:
                logger.warning(f'Unknown webhook status: {status}')
                return {
                    'success': False,
                    'error': f'Unknown status: {status}'
                }
            
            # Update additional payment info if available
            if 'Amount' in webhook_data:
                payment.amount = webhook_data['Amount']
            
            if 'Currency' in webhook_data:
                payment.currency = webhook_data['Currency']
            
            if 'CardMask' in webhook_data:
                payment.card_mask = webhook_data['CardMask']
            
            if 'Email' in webhook_data:
                payment.email = webhook_data['Email']
            
            db.session.commit()
            
            logger.info(f'Webhook processed for transaction {transaction_id}, status: {status}')
            
            return {
                'success': True,
                'message': f'Webhook processed successfully, status: {status}'
            }
            
        except Exception as e:
            logger.error(f'Error processing webhook: {str(e)}')
            return {
                'success': False,
                'error': str(e)
            }
    
    
    
    def refund_payment(self, transaction_id: str, amount: Optional[float] = None, user_id: int = None) -> Dict[str, Any]:
        """
        Refund payment (full or partial) via CloudPayments API
        
        Args:
            transaction_id: Payment transaction ID
            amount: Refund amount (None for full refund)
            user_id: ID of user processing refund
            
        Returns:
            Refund result
        """
        try:
            payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
            if not payment:
                return {
                    'success': False,
                    'error': 'Payment not found'
                }
            
            if payment.status != 'confirmed':
                return {
                    'success': False,
                    'error': 'Payment is not in confirmed status'
                }
            
            # Determine refund amount
            refund_amount = amount if amount is not None else float(payment.amount)
            
            if refund_amount > float(payment.amount):
                return {
                    'success': False,
                    'error': 'Refund amount cannot exceed payment amount'
                }
            
            # Call CloudPayments API to refund
            url = f"{self.base_url}/payments/refund"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Basic {self._get_auth_token()}'
            }
            
            data = {
                'TransactionId': int(transaction_id),
                'Amount': refund_amount
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('Success'):
                    if refund_amount == float(payment.amount):
                        payment.status = 'refunded_full'
                    else:
                        # Partial refund - in real implementation you might want to track this differently
                        payment.status = 'refunded_partial'
                    
                    db.session.commit()
                    
                    logger.info(f'Payment {transaction_id} refunded for amount {refund_amount} by user {user_id}')
                    
                    return {
                        'success': True,
                        'message': f'Refund processed for {refund_amount} {self.currency}',
                        'refund_amount': refund_amount
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('Message', 'Unknown error')
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text}'
                }
                
        except Exception as e:
            logger.error(f'Error refunding payment {transaction_id}: {str(e)}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def verify_webhook_signature(self, data: str, signature: str) -> bool:
        """
        Verify CloudPayments webhook signature
        
        Args:
            data: Raw request data
            signature: Signature from headers
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.api_secret:
            logger.error('API secret not configured - REJECTING webhook for security')
            return False  # ✅ ОТКЛОНЯЕМ, ЕСЛИ НЕТ СЕКРЕТА
        
        if not signature:
            logger.warning('No signature provided - REJECTING webhook')
            return False  # ✅ ОТКЛОНЯЕМ БЕЗ ПОДПИСИ
        
        try:
            import base64
            
            # Убираем префикс если есть
            clean_signature = signature.strip()
            if clean_signature.startswith('sha256='):
                clean_signature = clean_signature[7:]
            
            # CloudPayments отправляет подпись в формате base64, не hex
            # Вычисляем ожидаемую подпись
            # ВАЖНО: используем байты, не строку
            expected_signature_bytes = hmac.new(
                self.api_secret.encode('utf-8'),
                data.encode('utf-8'),
                hashlib.sha256
            ).digest()
            
            # Конвертируем в base64 для сравнения
            expected_signature_base64 = base64.b64encode(expected_signature_bytes).decode('utf-8')
            
            # Также попробуем hex формат для обратной совместимости
            expected_signature_hex = expected_signature_bytes.hex()
            
            # Логируем для отладки (всегда, не только debug)
            logger.info(f'=== SIGNATURE VERIFICATION ===')
            logger.info(f'Data length: {len(data)} bytes')
            logger.info(f'Data content (first 300 chars): {data[:300]}')
            logger.info(f'Received signature length: {len(clean_signature)}')
            logger.info(f'Received signature (first 50 chars): {clean_signature[:50] if clean_signature else "None"}...')
            logger.info(f'Expected signature (base64, first 50 chars): {expected_signature_base64[:50]}...')
            logger.info(f'API secret length: {len(self.api_secret)}')
            
            # Проверяем base64 формат (основной для CloudPayments)
            is_valid = hmac.compare_digest(clean_signature, expected_signature_base64)
            
            # Если base64 не подошел, пробуем hex
            if not is_valid and len(clean_signature) == 64:  # hex обычно 64 символа
                logger.info(f'Trying hex format comparison...')
                is_valid = hmac.compare_digest(clean_signature, expected_signature_hex)
            
            if not is_valid:
                logger.error(f'❌ INVALID webhook signature - REJECTING')
                logger.error(f'Expected (base64, full): {expected_signature_base64}')
                logger.error(f'Expected (hex, full): {expected_signature_hex}')
                logger.error(f'Got (full): {clean_signature}')
                logger.error(f'Data (full, first 500 chars): {data[:500]}')
                logger.error(f'Signature match (base64): {clean_signature == expected_signature_base64}')
                logger.error(f'Signature match (hex): {clean_signature == expected_signature_hex}')
                return False  # ✅ ОТКЛОНЯЕМ НЕВЕРНУЮ ПОДПИСЬ
            
            logger.info('Webhook signature verified successfully')
            return True
            
        except Exception as e:
            logger.error(f'Error verifying webhook signature: {str(e)} - REJECTING')
            import traceback
            logger.error(traceback.format_exc())
            return False  # ✅ ПРИ ОШИБКЕ ОТКЛОНЯЕМ
    
    def _get_auth_token(self) -> str:
        """Get base64 encoded auth token"""
        import base64
        auth_string = f"{self.public_id}:{self.api_secret}"
        return base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    def confirm_payment(self, transaction_id: str, amount: float = None, user_id: int = None) -> Dict[str, Any]:
        """
        Confirm (capture) payment for two-stage transactions
        
        Args:
            transaction_id: CloudPayments transaction ID
            amount: Amount to capture (if None, captures full amount)
            user_id: ID of user confirming payment
            
        Returns:
            Confirmation result
        """
        if not CLOUDPAYMENTS_AVAILABLE:
            return {'success': False, 'error': 'CloudPayments library not available'}
        
        try:
            payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
            if not payment:
                return {'success': False, 'error': 'Payment not found'}
            
            if payment.status != 'authorized':
                return {'success': False, 'error': 'Payment is not in authorized status'}
            
            # Prepare confirmation request
            confirm_data = {
                'TransactionId': transaction_id,
                'Amount': amount  # If None, will capture full authorized amount
            }
            
            # Make API request to confirm payment
            response = requests.post(
                f'{self.base_url}/payments/confirm',
                json=confirm_data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Basic {self._get_auth_token()}'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('Success'):
                    payment.status = 'confirmed'
                    payment.mom_confirmed = True
                    payment.confirmed_at = datetime.utcnow()
                    payment.confirmed_by = user_id
                    
                    db.session.commit()
                    
                    logger.info(f'Payment {transaction_id} confirmed successfully by user {user_id}')
                    return {'success': True, 'data': result}
                else:
                    logger.error(f'Payment confirmation failed: {result.get("Message")}')
                    return {'success': False, 'error': result.get('Message', 'Unknown error')}
            else:
                logger.error(f'Payment confirmation HTTP error: {response.status_code}')
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            logger.error(f'Error confirming payment {transaction_id}: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    def void_payment(self, transaction_id: str) -> Dict[str, Any]:
        """
        Void (cancel) authorized payment
        
        Args:
            transaction_id: CloudPayments transaction ID
            
        Returns:
            Void result
        """
        if not CLOUDPAYMENTS_AVAILABLE:
            return {'success': False, 'error': 'CloudPayments library not available'}
        
        try:
            payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
            if not payment:
                return {'success': False, 'error': 'Payment not found'}
            
            if payment.status != 'authorized':
                return {'success': False, 'error': 'Payment is not in authorized status'}
            
            # Check if payment can be voided (within 7 days)
            if not payment.can_be_voided():
                return {'success': False, 'error': 'Payment cannot be voided (older than 7 days)'}
            
            # Prepare void request
            void_data = {
                'TransactionId': transaction_id
            }
            
            # Make API request to void payment
            response = requests.post(
                f'{self.base_url}/payments/void',
                json=void_data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Basic {self._get_auth_token()}'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('Success'):
                    payment.status = 'voided'
                    payment.order.status = 'cancelled_unpaid'
                    
                    db.session.commit()
                    
                    logger.info(f'Payment {transaction_id} voided successfully')
                    return {'success': True, 'data': result}
                else:
                    logger.error(f'Payment void failed: {result.get("Message")}')
                    return {'success': False, 'error': result.get('Message', 'Unknown error')}
            else:
                logger.error(f'Payment void HTTP error: {response.status_code}')
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            logger.error(f'Error voiding payment {transaction_id}: {str(e)}')
            return {'success': False, 'error': str(e)}
