"""
CloudPayments Integration
Handles payment processing using CloudPayments API
"""

import hmac
import hashlib
import json
import requests
from datetime import timedelta
from typing import Dict, Optional, Any
from flask import current_app, request
from app.models import Order, Payment, User
from app import db
from app.utils.datetime_utils import moscow_now_naive
import logging

logger = logging.getLogger(__name__)

class CloudPaymentsAPI:
    """CloudPayments API integration"""
    
    def __init__(self):
        self.public_id = current_app.config.get('CLOUDPAYMENTS_PUBLIC_ID')
        self.api_secret = current_app.config.get('CLOUDPAYMENTS_API_SECRET')
        self.currency = current_app.config.get('CLOUDPAYMENTS_CURRENCY', 'RUB')
        self.base_url = 'https://api.cloudpayments.ru'
    
    def create_payment(self, order: Order) -> Dict[str, Any]:
        """
        Create payment authorization request
        
        Args:
            order: Order object
            
        Returns:
            Dict with payment data
        """
        try:
            # Prepare payment data
            payment_data = {
                'PublicId': self.public_id,
                'Amount': float(order.total_amount),
                'Currency': self.currency,
                'InvoiceId': order.order_number,
                'Description': f'Заказ видео {order.order_number}',
                'AccountId': str(order.customer_id),
                'Email': order.contact_email,
                'JsonData': {
                    'order_id': order.id,
                    'customer_id': order.customer_id,
                    'athlete_name': order.athlete.name,
                    'event_name': order.event.name
                }
            }
            
            # Create payment record
            payment = Payment(
                order_id=order.id,
                transaction_id='',  # Will be set after API call
                amount=order.total_amount,
                currency=self.currency,
                status='authorized',  # Will be set after API call
                email=order.contact_email
            )
            
            db.session.add(payment)
            db.session.commit()
            
            # For two-stage payment, we'll return the payment form data
            # In a real implementation, you would call CloudPayments API here
            payment_data['TransactionId'] = payment.id
            
            logger.info(f'Payment created for order {order.order_number}, payment ID: {payment.id}')
            
            return {
                'success': True,
                'payment_id': payment.id,
                'transaction_id': payment.id,
                'amount': float(order.total_amount),
                'currency': self.currency,
                'public_id': self.public_id,
                'description': payment_data['Description']
            }
            
        except Exception as e:
            logger.error(f'Error creating payment for order {order.order_number}: {str(e)}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def confirm_payment(self, transaction_id: str, user_id: int) -> Dict[str, Any]:
        """
        Confirm payment (charge money)
        
        Args:
            transaction_id: Payment transaction ID
            user_id: ID of user confirming payment
            
        Returns:
            Dict with confirmation result
        """
        try:
            payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
            if not payment:
                return {
                    'success': False,
                    'error': 'Payment not found'
                }
            
            if payment.status != 'authorized':
                return {
                    'success': False,
                    'error': 'Payment is not in authorized status'
                }
            
            # In a real implementation, you would call CloudPayments API to confirm
            # For now, we'll just update the status
            payment.status = 'confirmed'
            payment.mom_confirmed = True
            payment.confirmed_at = moscow_now_naive()
            payment.confirmed_by = user_id
            
            # Update order status if needed
            if payment.order.status == 'processing':
                # Order is already being processed, no need to change status
                pass
            
            db.session.commit()
            
            # Send payment success email to customer
            try:
                from app.utils.email import send_payment_success_email
                send_payment_success_email(payment.order)
                logger.info(f'Payment success email sent for order {payment.order.generated_order_number}')
            except Exception as e:
                logger.error(f'Failed to send payment success email: {e}')
                # Don't fail the whole operation if email fails
            
            logger.info(f'Payment {transaction_id} confirmed by user {user_id}')
            
            return {
                'success': True,
                'message': 'Payment confirmed successfully'
            }
            
        except Exception as e:
            logger.error(f'Error confirming payment {transaction_id}: {str(e)}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def void_payment(self, transaction_id: str) -> Dict[str, Any]:
        """
        Void (cancel) authorized payment
        
        Args:
            transaction_id: Payment transaction ID
            
        Returns:
            Dict with void result
        """
        try:
            payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
            if not payment:
                return {
                    'success': False,
                    'error': 'Payment not found'
                }
            
            if payment.status != 'authorized':
                return {
                    'success': False,
                    'error': 'Payment is not in authorized status'
                }
            
            # In a real implementation, you would call CloudPayments API to void
            payment.status = 'voided'
            
            # Cancel the order
            payment.order.status = 'cancelled'
            
            db.session.commit()
            
            logger.info(f'Payment {transaction_id} voided')
            
            return {
                'success': True,
                'message': 'Payment voided successfully'
            }
            
        except Exception as e:
            logger.error(f'Error voiding payment {transaction_id}: {str(e)}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def refund_payment(self, transaction_id: str, amount: Optional[float] = None, user_id: int = None) -> Dict[str, Any]:
        """
        Refund payment (full or partial)
        
        Args:
            transaction_id: Payment transaction ID
            amount: Refund amount (None for full refund)
            user_id: ID of user processing refund
            
        Returns:
            Dict with refund result
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
            
            # In a real implementation, you would call CloudPayments API to refund
            # For now, we'll just update the status
            if refund_amount == float(payment.amount):
                payment.status = 'refunded_full'
            else:
                # Partial refund
                payment.status = 'refunded_partial'
            
            db.session.commit()
            
            logger.info(f'Payment {transaction_id} refunded for amount {refund_amount} by user {user_id}')
            
            return {
                'success': True,
                'message': f'Refund processed for {refund_amount} {self.currency}',
                'refund_amount': refund_amount
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
            True if signature is valid
        """
        if not self.api_secret:
            logger.warning('API secret not configured, skipping signature verification')
            return True
        
        expected_signature = hmac.new(
            self.api_secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)

def process_webhook(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process CloudPayments webhook
    
    Args:
        webhook_data: Webhook payload
        
    Returns:
        Dict with processing result
    """
    try:
        transaction_id = webhook_data.get('TransactionId')
        status = webhook_data.get('Status')
        
        if not transaction_id or not status:
            return {
                'success': False,
                'error': 'Missing required fields in webhook'
            }
        
        # Find payment
        payment = Payment.query.filter_by(cp_transaction_id=transaction_id).first()
        if not payment:
            logger.warning(f'Payment not found for transaction {transaction_id}')
            return {
                'success': False,
                'error': 'Payment not found'
            }
        
        # Update payment status based on webhook
        if status == 'Authorized':
            payment.status = 'authorized'
            payment.order.status = 'paid'  # Payment authorized, order is now paid
            
        elif status == 'Completed':
            payment.status = 'confirmed'
            payment.mom_confirmed = True
            payment.confirmed_at = moscow_now_naive()
            
            # Send payment success email to customer
            try:
                from app.utils.email import send_payment_success_email
                send_payment_success_email(payment.order)
                logger.info(f'Payment success email sent for order {payment.order.generated_order_number}')
            except Exception as e:
                logger.error(f'Failed to send payment success email: {e}')
                # Don't fail the whole operation if email fails
            
        elif status == 'Voided':
            payment.status = 'voided'
            payment.order.status = 'cancelled_unpaid'
            
        elif status == 'Refunded':
            # CloudPayments doesn't distinguish partial/full in webhook, so we check amount
            refund_amount = webhook_data.get('Amount', 0)
            if refund_amount and float(refund_amount) < float(payment.amount):
                payment.status = 'refunded_partial'
            else:
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

def get_payment_form_data(order: Order) -> Dict[str, Any]:
    """
    Get payment form data for CloudPayments widget
    
    Args:
        order: Order object
        
    Returns:
        Dict with payment form configuration
    """
    api = CloudPaymentsAPI()
    payment_result = api.create_payment(order)
    
    if not payment_result['success']:
        return payment_result
    
    return {
        'success': True,
        'public_id': api.public_id,
        'amount': payment_result['amount'],
        'currency': payment_result['currency'],
        'description': payment_result['description'],
        'invoice_id': order.order_number,
        'account_id': str(order.customer_id),
        'email': order.contact_email,
        'json_data': {
            'order_id': order.id,
            'customer_id': order.customer_id,
            'athlete_name': order.athlete.name,
            'event_name': order.event.name
        },
        'success_url': f'/payment/success/{order.order_number}',
        'failure_url': f'/payment/failure/{order.order_number}'
    }
