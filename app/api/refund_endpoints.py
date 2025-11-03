from flask import request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Order, Payment, AuditLog
from app.utils.decorators import admin_or_mom_required
from app.utils.datetime_utils import moscow_now_naive
import logging

logger = logging.getLogger(__name__)

def register_refund_routes(bp):
    """Register refund-related routes"""
    
    @bp.route('/order/<int:order_id>/payment-info', methods=['GET'])
    @login_required
    @admin_or_mom_required
    def get_payment_info(order_id):
        """Get payment information for refund modal"""
        try:
            order = Order.query.get_or_404(order_id)
            
            # Calculate payment amounts
            total_paid = 0
            total_refunded = 0
            
            for payment in order.payments:
                if payment.status == 'confirmed':
                    total_paid += payment.amount
                elif payment.status in ['refunded_partial', 'refunded_full']:
                    total_refunded += payment.amount
            
            available_for_refund = total_paid - total_refunded
            
            return jsonify({
                'success': True,
                'paid_amount': total_paid,
                'refunded_amount': total_refunded,
                'available_for_refund': max(0, available_for_refund)
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error getting payment info: {str(e)}')
            return jsonify({'success': False, 'error': str(e)}), 500

    @bp.route('/order/<int:order_id>/refund', methods=['POST'])
    @login_required
    @admin_or_mom_required
    def process_refund(order_id):
        """Process refund for order"""
        try:
            order = Order.query.get_or_404(order_id)
            
            # Get form data
            refund_amount = float(request.form.get('refund_amount', 0))
            refund_reason = request.form.get('refund_reason', '')
            refund_comment = request.form.get('refund_comment', '')
            
            if refund_amount <= 0:
                return jsonify({'success': False, 'error': 'Неверная сумма возврата'}), 400
            
            # Check if order has payments
            confirmed_payments = [p for p in order.payments if p.status == 'confirmed']
            if not confirmed_payments:
                return jsonify({'success': False, 'error': 'Заказ не оплачен'}), 400
            
            # Calculate available refund amount
            total_paid = sum(p.amount for p in confirmed_payments)
            total_refunded = sum(p.amount for p in order.payments if p.status in ['refunded_partial', 'refunded_full'])
            available_for_refund = total_paid - total_refunded
            
            if refund_amount > available_for_refund:
                return jsonify({'success': False, 'error': f'Сумма возврата превышает доступную сумму ({available_for_refund:.2f} ₽)'}), 400
            
            # Determine if this is a full or partial refund
            is_full_refund = refund_amount >= available_for_refund
            
            # Create refund payment record
            now = moscow_now_naive()
            refund_payment = Payment(
                order_id=order.id,
                amount=refund_amount,
                status='refunded_full' if is_full_refund else 'refunded_partial',
                method=None,  # Refund doesn't have payment method
                cp_transaction_id=f'REFUND_{order.id}_{int(now.timestamp())}',
                created_at=now,
                processed_at=now,
                notes=f'Причина: {refund_reason}. {refund_comment}' if refund_comment else f'Причина: {refund_reason}'
            )
            
            db.session.add(refund_payment)
            
            # Update order status based on refund type
            if is_full_refund:
                order.status = 'refunded_full'
            else:
                order.status = 'completed_partial_refund'
            order.processed_at = now
            
            db.session.commit()
            
            # Log action
            AuditLog.create_log(
                user_id=current_user.id,
                action='ORDER_REFUND',
                resource_type='Order',
                resource_id=str(order.id),
                details={
                    'refund_amount': refund_amount,
                    'refund_reason': refund_reason,
                    'refund_comment': refund_comment
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            return jsonify({
                'success': True,
                'message': f'Возврат {refund_amount:.2f} ₽ успешно обработан'
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
