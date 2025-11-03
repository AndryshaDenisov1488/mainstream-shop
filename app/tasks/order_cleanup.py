"""
Background task for automatic order cancellation
Cancels orders that have expired payment deadlines
"""

import logging
from datetime import timedelta
from flask import current_app
from app import db
from app.models import Order, AuditLog
from app.utils.cloudpayments import CloudPaymentsAPI
from app.utils.datetime_utils import moscow_now_naive

logger = logging.getLogger(__name__)

def cancel_expired_orders_with_context():
    """Wrapper that creates app context for cancel_expired_orders"""
    # Получаем app из глобальной переменной scheduler
    from app.tasks.scheduler import _app_instance
    if _app_instance:
        logger.debug('Using _app_instance for cancel_expired_orders')
        with _app_instance.app_context():
            cancel_expired_orders()
    else:
        # Fallback: пытаемся использовать current_app если доступен
        try:
            from flask import current_app
            logger.debug('Using current_app for cancel_expired_orders')
            with current_app.app_context():
                cancel_expired_orders()
        except RuntimeError as e:
            logger.error(f'No application context available for cancel_expired_orders: {str(e)}')

def cancel_expired_orders():
    """
    Cancel orders that have expired payment deadlines
    Runs every minute via APScheduler
    """
    try:
        logger.info('Starting cancel_expired_orders task')
        
        # Get auto_cancel_minutes from settings
        try:
            from app.utils.settings import get_auto_cancel_minutes
            auto_cancel_minutes = get_auto_cancel_minutes()
            logger.debug(f'Using auto_cancel_minutes from settings: {auto_cancel_minutes} minutes')
        except Exception as e:
            logger.warning(f'Failed to get auto_cancel_minutes from settings, using default 15 minutes: {e}')
            auto_cancel_minutes = 15  # Default fallback: 15 minutes
        
        # Find orders with expired payment deadlines
        # Проверяем как заказы с payment_expires_at, так и старые заказы без него (созданные более auto_cancel_minutes назад)
        current_time = moscow_now_naive()
        expired_threshold = current_time - timedelta(minutes=auto_cancel_minutes)
        
        logger.debug(f'Checking for expired orders (current_time={current_time}, expired_threshold={expired_threshold})')
        
        expired_orders = Order.query.filter(
            Order.status == 'awaiting_payment'
        ).filter(
            db.or_(
                # Либо payment_expires_at установлен и истек
                db.and_(
                    Order.payment_expires_at.isnot(None),
                    Order.payment_expires_at < current_time
                ),
                # Либо payment_expires_at не установлен, но заказ старше auto_cancel_minutes
                db.and_(
                    Order.payment_expires_at.is_(None),
                    Order.created_at < expired_threshold
                )
            )
        ).all()
        
        if not expired_orders:
            logger.debug('No expired orders found')
            return
        
        logger.info(f'Found {len(expired_orders)} expired orders to cancel')
        
        cp_api = CloudPaymentsAPI()
        
        for order in expired_orders:
            try:
                # ✅ Обновляем статус заказа (Flask уже создал транзакцию для app context)
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
                
                # ✅ Log the cancellation
                AuditLog.create_log(
                    user_id=None,  # System action
                    action='ORDER_AUTO_CANCELLED_TIMEOUT',
                    resource_type='Order',
                    resource_id=str(order.id),
                    details={
                        'order_number': order.order_number,
                        'expired_at': order.payment_expires_at.isoformat() if order.payment_expires_at else None,
                        'payment_intent_id': order.payment_intent_id
                    },
                    ip_address=None,
                    user_agent='System Task',
                    commit=False  # ✅ Коммитим вместе с заказом
                )
                
                # Коммитим транзакцию
                db.session.commit()
                
                logger.info(f'Order {order.id} ({order.order_number}) cancelled due to payment timeout')
                
            except Exception as e:
                logger.error(f'Error cancelling order {order.id}: {str(e)}')
                db.session.rollback()  # ✅ Откат текущей транзакции
                continue
        
        logger.info(f'Successfully cancelled {len(expired_orders)} expired orders')
        
    except Exception as e:
        logger.error(f'Error in cancel_expired_orders task: {str(e)}')
        try:
            db.session.rollback()
        except Exception:
            pass  # Если нет активной сессии, просто пропускаем
        import traceback
        logger.error(traceback.format_exc())

def cleanup_old_audit_logs_with_context():
    """Wrapper that creates app context for cleanup_old_audit_logs"""
    # Получаем app из глобальной переменной scheduler
    from app.tasks.scheduler import _app_instance
    if _app_instance:
        with _app_instance.app_context():
            cleanup_old_audit_logs()
    else:
        # Fallback: пытаемся использовать current_app если доступен
        try:
            from flask import current_app
            with current_app.app_context():
                cleanup_old_audit_logs()
        except RuntimeError:
            logger.error('No application context available for cleanup_old_audit_logs')

def cleanup_old_audit_logs():
    """
    Clean up old audit logs (older than 1 year)
    Runs daily via APScheduler
    """
    try:
        cutoff_date = moscow_now_naive() - timedelta(days=365)
        
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
