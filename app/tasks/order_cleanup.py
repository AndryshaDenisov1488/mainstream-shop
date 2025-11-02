"""
Background task for automatic order cancellation
Cancels orders that have expired payment deadlines
"""

import logging
from datetime import datetime, timedelta
from flask import current_app
from app import db
from app.models import Order, AuditLog
from app.utils.cloudpayments import CloudPaymentsAPI

logger = logging.getLogger(__name__)

def cancel_expired_orders():
    """
    Cancel orders that have expired payment deadlines
    Runs every minute via APScheduler
    """
    try:
        # Find orders with expired payment deadlines
        expired_orders = Order.query.filter(
            Order.status == 'awaiting_payment',
            Order.payment_expires_at < datetime.utcnow()
        ).all()
        
        if not expired_orders:
            logger.debug('No expired orders found')
            return
        
        logger.info(f'Found {len(expired_orders)} expired orders to cancel')
        
        cp_api = CloudPaymentsAPI()
        
        for order in expired_orders:
            try:
                # ✅ Использовать транзакцию для каждого заказа
                with db.session.begin():
                    # Update order status
                    order.status = 'cancelled_unpaid'
                    order.cancellation_reason = 'timeout'
                    
                    # Try to void payment if it exists and is authorized
                    if order.payment_intent_id:
                        payment = order.payments.filter_by(
                            cp_transaction_id=order.payment_intent_id,
                            status='authorized'
                        ).first()
                        
                        if payment:
                            # Void the authorized payment
                            void_result = cp_api.void_payment(order.payment_intent_id)
                            if void_result.get('success'):
                                payment.status = 'voided'
                                logger.info(f'Payment {order.payment_intent_id} voided for expired order {order.id}')
                            else:
                                logger.warning(f'Failed to void payment {order.payment_intent_id}: {void_result.get("error")}')
                    
                    # ✅ Log the cancellation БЕЗ отдельного коммита
                    AuditLog.create_log(
                        user_id=None,  # System action
                        action='ORDER_AUTO_CANCELLED_TIMEOUT',
                        resource_type='Order',
                        resource_id=str(order.id),
                        details={
                            'order_number': order.order_number,
                            'expired_at': order.payment_expires_at.isoformat(),
                            'payment_intent_id': order.payment_intent_id
                        },
                        ip_address=None,
                        user_agent='System Task',
                        commit=False  # ✅ Не коммитить отдельно
                    )
                    
                    # Коммит произойдет автоматически при выходе из with db.session.begin()
                
                logger.info(f'Order {order.id} ({order.order_number}) cancelled due to payment timeout')
                
            except Exception as e:
                logger.error(f'Error cancelling order {order.id}: {str(e)}')
                db.session.rollback()  # ✅ Откат текущей транзакции
                continue
        
        logger.info(f'Successfully cancelled {len(expired_orders)} expired orders')
        
    except Exception as e:
        logger.error(f'Error in cancel_expired_orders task: {str(e)}')
        db.session.rollback()
        raise

def cleanup_old_audit_logs():
    """
    Clean up old audit logs (older than 1 year)
    Runs daily via APScheduler
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=365)
        
        # ✅ Удаляем батчами по 1000 записей для избежания проблем с памятью
        deleted_count = 0
        batch_size = 1000
        
        while True:
            batch = AuditLog.query.filter(
                AuditLog.created_at < cutoff_date
            ).limit(batch_size).all()
            
            if not batch:
                break
            
            try:
                for log in batch:
                    db.session.delete(log)
                
                db.session.commit()
                deleted_count += len(batch)
                logger.info(f'Deleted batch of {len(batch)} audit logs (total: {deleted_count})')
            except Exception as e:
                logger.error(f'Error deleting batch of audit logs: {str(e)}')
                db.session.rollback()
                raise
        
        if deleted_count > 0:
            logger.info(f'Successfully cleaned up {deleted_count} old audit logs')
        else:
            logger.debug('No old audit logs to clean up')
            
    except Exception as e:
        logger.error(f'Error in cleanup_old_audit_logs task: {str(e)}')
        db.session.rollback()
        raise
