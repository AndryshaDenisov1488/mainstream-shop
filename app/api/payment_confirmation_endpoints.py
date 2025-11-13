from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Order, Payment, AuditLog
from app.utils.decorators import role_required
from app.utils.email import send_email
from app.utils.datetime_utils import moscow_now_naive
import logging

logger = logging.getLogger(__name__)

def register_payment_confirmation_routes(bp):
    """Register payment confirmation routes for mom"""
    
    @bp.route('/order/<int:order_id>/confirm-payment', methods=['POST'])
    @login_required
    @role_required('MOM')
    def confirm_payment(order_id):
        """Mom confirms payment receipt in bank"""
        try:
            order = Order.query.get_or_404(order_id)
            
            # Validate order status - можно подтвердить для links_sent (с частичным возвратом или без)
            if order.status not in ['completed', 'refund_required', 'links_sent', 'completed_partial_refund']:
                return jsonify({
                    'success': False, 
                    'error': 'Заказ должен быть выполнен, требовать возврата или иметь отправленные ссылки'
                }), 400
            
            # Get confirmed payments for this order - сначала ищем authorized, потом confirmed
            confirmed_payments = Payment.query.filter(
                Payment.order_id == order.id,
                Payment.status == 'authorized',
                Payment.mom_confirmed == False
            ).all()
            
            # Если нет authorized, но есть confirmed без mom_confirmed - тоже можно подтвердить получение
            if not confirmed_payments:
                confirmed_payments = Payment.query.filter(
                    Payment.order_id == order.id,
                    Payment.status == 'confirmed',
                    Payment.mom_confirmed == False
                ).all()
            
            if not confirmed_payments:
                return jsonify({
                    'success': False, 
                    'error': 'Нет неподтвержденных платежей для этого заказа'
                }), 400
            
            # Confirm all payments
            total_amount = 0
            for payment in confirmed_payments:
                payment.mom_confirmed = True
                payment.confirmed_at = moscow_now_naive()
                payment.confirmed_by = current_user.id
                payment.status = 'confirmed'
                total_amount += float(payment.amount)
            
            # Update order status to completed if it was links_sent
            if order.status == 'links_sent':
                order.status = 'completed'
                order.processed_at = moscow_now_naive()
            
            db.session.commit()
            
            # Log action
            AuditLog.create_log(
                user_id=current_user.id,
                action='PAYMENT_CONFIRMED',
                resource_type='Order',
                resource_id=str(order.id),
                details={
                    'total_amount': total_amount,
                    'payments_count': len(confirmed_payments),
                    'order_status': order.status
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            # Send email to customer
            try:
                send_payment_confirmation_email(order, total_amount)
            except Exception as e:
                logger.error(f'Failed to send payment confirmation email: {e}')
            
            return jsonify({
                'success': True,
                'message': f'Платеж {total_amount:.2f} ₽ успешно подтвержден',
                'total_amount': total_amount
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error confirming payment: {str(e)}')
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @bp.route('/order/<int:order_id>/process-refund', methods=['POST'])
    @login_required
    @role_required('MOM')
    def mom_process_refund(order_id):
        """Mom processes refund for order"""
        try:
            order = Order.query.get_or_404(order_id)
            
            # Get form data
            refund_amount = float(request.form.get('refund_amount', 0))
            refund_reason = request.form.get('refund_reason', '')
            
            if refund_amount <= 0:
                return jsonify({
                    'success': False, 
                    'error': 'Неверная сумма возврата'
                }), 400
            
            # Check if payments are confirmed by mom
            confirmed_payments = Payment.query.filter(
                Payment.order_id == order.id,
                Payment.status == 'confirmed',
                Payment.mom_confirmed == True
            ).all()
            
            if not confirmed_payments:
                return jsonify({
                    'success': False, 
                    'error': 'Сначала необходимо подтвердить поступление платежа'
                }), 400
            
            # Calculate available refund amount
            total_confirmed = sum(float(p.amount) for p in confirmed_payments)
            total_refunded = sum(float(p.amount) for p in order.payments if p.status in ['refunded_partial', 'refunded_full'])
            available_for_refund = total_confirmed - total_refunded
            
            if refund_amount > available_for_refund:
                return jsonify({
                    'success': False, 
                    'error': f'Сумма возврата превышает доступную сумму ({available_for_refund:.2f} ₽)'
                }), 400
            
            # Create refund payment record
            is_full_refund = refund_amount >= available_for_refund
            now = moscow_now_naive()
            refund_payment = Payment(
                order_id=order.id,
                amount=refund_amount,
                status='refunded_full' if is_full_refund else 'refunded_partial',
                method=None,  # Refund doesn't have payment method
                cp_transaction_id=f'REFUND_{order.id}_{int(now.timestamp())}',
                mom_confirmed=True,
                confirmed_at=now,
                confirmed_by=current_user.id,
                created_at=now,
                processed_at=now,
                notes=f'Причина: {refund_reason}'
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
                action='PAYMENT_REFUND',
                resource_type='Order',
                resource_id=str(order.id),
                details={
                    'refund_amount': refund_amount,
                    'refund_reason': refund_reason,
                    'remaining_amount': available_for_refund - refund_amount
                },
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            # Send email to customer
            try:
                send_refund_confirmation_email(order, refund_amount, refund_reason)
            except Exception as e:
                logger.error(f'Failed to send refund confirmation email: {e}')
            
            return jsonify({
                'success': True,
                'message': f'Возврат {refund_amount:.2f} ₽ успешно обработан'
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error processing refund: {str(e)}')
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @bp.route('/order/<int:order_id>/payment-history', methods=['GET'])
    @login_required
    @role_required('MOM')
    def get_payment_history(order_id):
        """Get payment history for order"""
        try:
            order = Order.query.get_or_404(order_id)
            
            payments = Payment.query.filter(Payment.order_id == order.id).order_by(
                Payment.created_at.desc()
            ).all()
            
            payment_history = []
            for payment in payments:
                payment_history.append({
                    'id': payment.id,
                    'transaction_id': payment.cp_transaction_id,
                    'amount': float(payment.amount),
                    'status': payment.status,
                    'payment_method': payment.payment_method,
                    'mom_confirmed': payment.mom_confirmed,
                    'confirmed_at': payment.confirmed_at.isoformat() if payment.confirmed_at else None,
                    'confirmed_by': payment.confirmer.full_name if payment.confirmer else None,
                    'created_at': payment.created_at.isoformat(),
                    'processed_at': payment.processed_at.isoformat() if payment.processed_at else None
                })
            
            return jsonify({
                'success': True,
                'payments': payment_history
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error getting payment history: {str(e)}')
            return jsonify({'success': False, 'error': str(e)}), 500

def send_payment_confirmation_email(order, amount):
    """Send email to customer about payment confirmation"""
    subject = f"Платеж по заказу {order.generated_order_number} подтвержден"
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [order.contact_email]
    
    text_content = (
        f"Платеж подтвержден.\n\n"
        f"Ваш платеж по заказу {order.generated_order_number} на сумму {amount:.2f} ₽ успешно подтвержден.\n"
        "Спасибо за покупку!"
    )
    
    html_content = f"""
    <h2>Платеж подтвержден</h2>
    <p>Ваш платеж по заказу <strong>{order.generated_order_number}</strong> в размере <strong>{amount:.2f} ₽</strong> успешно подтвержден.</p>
    <p>Спасибо за покупку!</p>
    """
    
    send_email(subject, sender, recipients, text_content, html_content)

def send_refund_confirmation_email(order, amount, reason):
    """Send email to customer about refund"""
    subject = f"Возврат по заказу {order.generated_order_number}"
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [order.contact_email]
    
    text_content = (
        f"Возврат обработан.\n\n"
        f"По заказу {order.generated_order_number} оформлен возврат на сумму {amount:.2f} ₽.\n"
        f"Причина: {reason or 'не указана'}\n"
        "Деньги будут возвращены в течение 3-5 рабочих дней."
    )
    
    html_content = f"""
    <h2>Возврат обработан</h2>
    <p>По вашему заказу <strong>{order.generated_order_number}</strong> обработан возврат в размере <strong>{amount:.2f} ₽</strong>.</p>
    <p><strong>Причина:</strong> {reason or 'не указана'}</p>
    <p>Деньги будут возвращены в течение 3-5 рабочих дней.</p>
    """
    
    send_email(subject, sender, recipients, text_content, html_content)
