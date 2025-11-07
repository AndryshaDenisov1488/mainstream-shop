from flask import current_app, render_template, url_for
from flask_mail import Message
from app import mail
from app.models import User, VideoType
import logging

logger = logging.getLogger(__name__)

def send_email(subject, sender, recipients, text_body, html_body):
    """Send email using Flask-Mail"""
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    mail.send(msg)

def send_user_credentials_email(user, password):
    """Send user credentials email"""
    subject = 'Добро пожаловать в MainStream Shop'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [user.email]
    
    text_body = render_template('email/user_credentials.txt',
                               user=user, password=password)
    html_body = render_template('email/user_credentials.html',
                               user=user, password=password)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_password_reset_email(user):
    """Send password reset email"""
    token = user.get_reset_password_token()
    subject = 'Сброс пароля - MainStream Shop'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [user.email]
    
    text_body = render_template('email/reset_password.txt',
                               user=user, token=token)
    html_body = render_template('email/reset_password.html',
                               user=user, token=token)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_new_password_email(user, new_password):
    """Send new password email"""
    subject = 'Новый пароль - MainStream Shop'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [user.email]
    
    text_body = render_template('email/new_password.txt',
                               user=user, password=new_password)
    html_body = render_template('email/new_password.html',
                               user=user, password=new_password)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_order_confirmation_email(order):
    """Send order confirmation email"""
    subject = f'Подтверждение заказа {order.generated_order_number}'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [order.contact_email]
    
    text_body = render_template('email/order_confirmation.txt', order=order)
    html_body = render_template('email/order_confirmation.html', order=order)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_video_links_email(order):
    """Send video links email"""
    subject = f'Ваши видео готовы! Заказ {order.generated_order_number}'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [order.contact_email]
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    text_body = render_template('email/video_links.txt', order=order, video_types_dict=video_types_dict)
    html_body = render_template('email/video_links.html', order=order, video_types_dict=video_types_dict)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_link_expiry_reminder_email(order):
    """Send link expiry reminder email"""
    subject = f'Ссылки на видео истекают - Заказ {order.generated_order_number}'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [order.contact_email]
    
    text_body = render_template('email/link_expiry_reminder.txt', order=order)
    html_body = render_template('email/link_expiry_reminder.html', order=order)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_order_cancellation_email(order, cancellation_reason=None):
    """Send order cancellation email"""
    subject = f'Заказ отменен - {order.generated_order_number}'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [order.contact_email]
    
    text_body = render_template('email/order_cancelled.txt', 
                               order=order, cancellation_reason=cancellation_reason)
    html_body = render_template('email/order_cancelled.html', 
                               order=order, cancellation_reason=cancellation_reason)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_payment_success_email(order):
    """Send payment success email to customer"""
    subject = f'Оплата получена! Заказ {order.generated_order_number} принят в работу'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [order.contact_email]
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    text_body = render_template('email/payment_success.txt', order=order, video_types_dict=video_types_dict)
    html_body = render_template('email/payment_success.html', order=order, video_types_dict=video_types_dict)
    
    send_email(subject, sender, recipients, text_body, html_body)

def send_order_ready_notification(order):
    """Send notification about ready order to mom/admin"""
    subject = f'✅ Заказ готов к приёму денег: {order.generated_order_number}'
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    
    # Get mom and admin emails
    from app.models import User
    recipients = []
    
    # Add mom users
    moms = User.query.filter_by(role='MOM', is_active=True).all()
    for mom in moms:
        recipients.append(mom.email)
    
    # Add admin users
    admins = User.query.filter_by(role='ADMIN', is_active=True).all()
    for admin in admins:
        recipients.append(admin.email)
    
    if not recipients:
        logger.warning("No mom/admin users found for notification")
        return
    
    text_body = f"""
✅ Заказ {order.generated_order_number} готов к приёму денег!

Спортсмен: {order.athlete.name}
Турнир: {order.event.name}
Клиент: {order.contact_email}
Сумма: {order.total_amount:.2f} ₽

Ссылки на видео отправлены клиенту.
Необходимо подтвердить получение денег в панели MOM.

Войти в панель: {url_for('mom.dashboard', _external=True)}
"""
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Заказ готов к приёму денег</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #28a745;">✅ Заказ готов к приёму денег!</h2>
        
        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3>Информация о заказе:</h3>
            <p><strong>Номер заказа:</strong> {order.generated_order_number}</p>
            <p><strong>Спортсмен:</strong> {order.athlete.name}</p>
            <p><strong>Турнир:</strong> {order.event.name}</p>
            <p><strong>Клиент:</strong> {order.contact_email}</p>
            <p><strong>Сумма:</strong> {order.total_amount:.2f} ₽</p>
        </div>
        
        <div style="background: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <p><strong>✅ Ссылки на видео отправлены клиенту</strong></p>
            <p>Необходимо подтвердить получение денег в панели MOM.</p>
        </div>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{url_for('mom.dashboard', _external=True)}" 
               style="background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">
                Войти в панель управления
            </a>
        </div>
        
        <hr>
        <p style="font-size: 12px; color: #666;">
            MainStream Shop - Профессиональные видео с турниров по фигурному катанию
        </p>
    </div>
</body>
</html>
"""
    
    send_email(subject, sender, recipients, text_body, html_body)


def send_chat_notification_email(recipient, order, message, sender):
    """Send chat notification email"""
    subject = f'Новое сообщение в чате заказа №{order.generated_order_number}'
    sender_email = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [recipient.email]
    
    text_body = render_template('email/chat_notification.txt',
                               recipient=recipient, order=order, message=message, sender=sender)
    html_body = render_template('email/chat_notification.html',
                               recipient=recipient, order=order, message=message, sender=sender)
    
    send_email(subject, sender_email, recipients, text_body, html_body)
