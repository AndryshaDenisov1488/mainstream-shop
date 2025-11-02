from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

class User(UserMixin, db.Model):
    """User model with role-based access control"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    telegram_id = db.Column(db.String(50), nullable=True, unique=True, index=True)
    role = db.Column(db.Enum('ADMIN', 'MOM', 'OPERATOR', 'CUSTOMER', name='user_roles'), 
                     nullable=False, default='CUSTOMER')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    orders = db.relationship('Order', backref='customer', lazy='dynamic', foreign_keys='Order.customer_id')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic', foreign_keys='AuditLog.user_id')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password hash"""
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def generate_password():
        """Generate random password with letters and numbers (minimum 8 characters)"""
        import secrets
        import string
        
        letters = string.ascii_letters
        numbers = string.digits
        password = []
        
        # Ensure at least one letter and one number
        password.append(secrets.choice(letters))
        password.append(secrets.choice(numbers))
        
        # Fill the rest with random characters (letters and numbers)
        alphabet = letters + numbers
        for _ in range(8):  # Total length 10 characters
            password.append(secrets.choice(alphabet))
        
        # Shuffle the password
        secrets.SystemRandom().shuffle(password)
        return ''.join(password)
    
    def get_reset_password_token(self, expires_in=600):
        """Generate password reset token"""
        import jwt
        import time
        
        return jwt.encode(
            {'reset_password': self.id, 'exp': time.time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256')
    
    @staticmethod
    def verify_reset_password_token(token):
        """Verify password reset token"""
        import jwt
        
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                           algorithms=['HS256'])['reset_password']
        except:
            return None
        return User.query.get(id)
    
    def __repr__(self):
        return f'<User {self.email}>'

class Event(db.Model):
    """Tournament event model"""
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    place = db.Column(db.String(200))
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    categories = db.relationship('Category', backref='event', lazy='dynamic', cascade='all, delete-orphan')
    event_orders = db.relationship('Order', lazy='dynamic')
    
    def __repr__(self):
        return f'<Event {self.name}>'

class Category(db.Model):
    """Competition category model"""
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.Enum('M', 'F', 'MIXED', name='gender_types'), nullable=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    
    # Relationships
    athletes = db.relationship('Athlete', backref='category', lazy='dynamic', cascade='all, delete-orphan')
    category_orders = db.relationship('Order', lazy='dynamic')
    
    def __repr__(self):
        return f'<Category {self.name} - {self.event.name}>'

class Athlete(db.Model):
    """Athlete participant model"""
    __tablename__ = 'athletes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    birth_date = db.Column(db.Date)
    gender = db.Column(db.Enum('M', 'F', name='athlete_gender'), nullable=True)
    club_name = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    is_pair = db.Column(db.Boolean, default=False)
    partner_name = db.Column(db.String(100))
    
    # Relationships
    athlete_orders = db.relationship('Order', lazy='dynamic')
    
    def __repr__(self):
        return f'<Athlete {self.name}>'

class VideoType(db.Model):
    """Video type model"""
    __tablename__ = 'video_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<VideoType {self.name}>'

class Order(db.Model):
    """Order model"""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    generated_order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # Human-readable order number
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'), nullable=False)
    
    # Order details
    video_types = db.Column(db.JSON, nullable=False)  # List of video type IDs
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum('draft', 'checkout_initiated', 'awaiting_payment', 'paid', 'processing', 'awaiting_info', 'ready', 'links_sent', 'completed', 'completed_partial_refund', 'cancelled_unpaid', 'cancelled_manual', 'refunded_partial', 'refunded_full', name='order_status'),
                       default='draft', nullable=False)
    
    # Payment information
    payment_intent_id = db.Column(db.String(100), nullable=True, index=True)
    payment_method = db.Column(db.Enum('card', 'sbp', 'unknown', name='payment_method_types'), nullable=True)
    payment_expires_at = db.Column(db.DateTime, nullable=True, index=True)
    paid_amount = db.Column(db.Numeric(10, 2), default=0)
    currency = db.Column(db.String(3), default='RUB')
    
    # Contact information
    contact_email = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=True)
    contact_first_name = db.Column(db.String(50), nullable=True)
    contact_last_name = db.Column(db.String(50), nullable=True)
    comment = db.Column(db.Text)
    
    # Child information
    child_first_name = db.Column(db.String(50), nullable=True)
    child_last_name = db.Column(db.String(50), nullable=True)
    child_birth_date = db.Column(db.Date, nullable=True)
    child_gender = db.Column(db.Enum('male', 'female', name='child_gender'), nullable=True)
    child_team = db.Column(db.String(100), nullable=True)
    child_coach = db.Column(db.String(100), nullable=True)
    
    # Processing information
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    processed_at = db.Column(db.DateTime)
    video_links = db.Column(db.JSON)  # Dict with video type IDs as keys and links as values
    notes = db.Column(db.Text)  # Notes from operator to mom
    operator_comment = db.Column(db.Text)  # Comments from operator about the order
    refund_reason = db.Column(db.Text)  # Reason for refund (separate from operator comment)
    cancellation_reason = db.Column(db.Text)  # Reason for order cancellation
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    payments = db.relationship('Payment', backref='order', lazy='dynamic')
    operator = db.relationship('User', foreign_keys=[operator_id], backref='processed_orders')
    athlete = db.relationship('Athlete', overlaps="athlete_orders")
    event = db.relationship('Event', overlaps="event_orders")
    category = db.relationship('Category', overlaps="category_orders")
    
    @staticmethod
    def generate_order_number():
        """Generate unique order number (internal)"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f'MS{timestamp}'
    
    @staticmethod
    def generate_human_order_number():
        """Generate human-readable order number"""
        import uuid
        # Format: MS-YYYYMMDD-XXXX
        date_str = datetime.now().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4())[:4].upper()
        return f'MS-{date_str}-{unique_id}'
    
    def is_overdue(self):
        """Check if order is overdue (older than 4 days)"""
        if self.status == 'processing':
            return datetime.utcnow() - self.created_at > timedelta(days=4)
        return False
    
    def is_payment_expired(self):
        """Check if payment has expired (15 minutes TTL)"""
        if self.status == 'awaiting_payment' and self.payment_expires_at:
            return datetime.utcnow() > self.payment_expires_at
        return False
    
    def can_be_taken_by_operator(self):
        """Check if order can be taken by operator"""
        return self.status == 'paid'
    
    def can_be_captured_by_mom(self):
        """Check if order can be captured by mom"""
        return self.status in ['ready', 'links_sent']
    
    def get_video_links_expiry(self):
        """Get video links expiry date"""
        if self.processed_at:
            return self.processed_at + timedelta(days=90)
        return None
    
    def get_status_display(self):
        """Get Russian display name for order status"""
        status_map = {
            'draft': 'Черновик',
            'checkout_initiated': 'Оформление инициировано',
            'awaiting_payment': 'Ожидание оплаты',
            'paid': 'Оплачен',
            'processing': 'В обработке',
            'ready': 'Готов к отправке',
            'links_sent': 'Ссылки отправлены',
            'completed': 'Выполнен',
            'cancelled_unpaid': 'Отменен (не оплачен)',
            'cancelled_manual': 'Отменен вручную',
            'refunded_partial': 'Частичный возврат',
            'refunded_full': 'Полный возврат'
        }
        return status_map.get(self.status, self.status)
    
    def __repr__(self):
        return f'<Order {self.order_number}>'

class Payment(db.Model):
    """Payment model for CloudPayments integration"""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    
    # CloudPayments data
    cp_transaction_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RUB')
    status = db.Column(db.Enum('authorized', 'confirmed', 'voided', 'refunded_partial', 'refunded_full', 'failed', name='payment_status'),
                       default='authorized', nullable=False)
    
    # Payment details
    method = db.Column(db.Enum('card', 'sbp', name='payment_method_enum'))
    card_mask = db.Column(db.String(20))  # Last 4 digits
    email = db.Column(db.String(120))
    raw_payload = db.Column(db.JSON)  # Raw webhook data for audit
    
    # Processing information
    mom_confirmed = db.Column(db.Boolean, default=False)
    confirmed_at = db.Column(db.DateTime)
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    confirmer = db.relationship('User', foreign_keys=[confirmed_by], backref='confirmed_payments')
    
    def can_be_voided(self):
        """Check if payment can be voided (within 7 days)"""
        return (self.status == 'authorized' and 
                datetime.utcnow() - self.created_at <= timedelta(days=7))
    
    def __repr__(self):
        return f'<Payment {self.transaction_id}>'

class AuditLog(db.Model):
    """Audit log for tracking user actions"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.String(50))
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @staticmethod
    def create_log(user_id=None, action=None, resource_type=None, resource_id=None, 
                   details=None, ip_address=None, user_agent=None):
        """Create audit log entry"""
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(log)
        db.session.commit()
        return log
    
    @staticmethod
    def log_user_action(user_id, action, ip_address=None, user_agent=None, details=None):
        """Log user action (login, logout, etc.)"""
        return AuditLog.create_log(
            user_id=user_id,
            action=action,
            resource_type='user',
            resource_id=str(user_id),
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
    
    @staticmethod
    def log_order_action(user_id, action, order_id, ip_address=None, user_agent=None, details=None):
        """Log order-related action"""
        return AuditLog.create_log(
            user_id=user_id,
            action=action,
            resource_type='order',
            resource_id=str(order_id),
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
    
    @staticmethod
    def log_payment_action(user_id, action, payment_id, ip_address=None, user_agent=None, details=None):
        """Log payment-related action"""
        return AuditLog.create_log(
            user_id=user_id,
            action=action,
            resource_type='payment',
            resource_id=str(payment_id),
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
    
    @staticmethod
    def log_admin_action(user_id, action, resource_type, resource_id, ip_address=None, user_agent=None, details=None):
        """Log admin action"""
        return AuditLog.create_log(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
    
    @staticmethod
    def log_telegram_action(telegram_id, action, details=None):
        """Log Telegram bot action"""
        return AuditLog.create_log(
            user_id=None,
            action=f'TELEGRAM_{action}',
            resource_type='telegram',
            resource_id=telegram_id,
            details=details
        )
    
    @property
    def action_display(self):
        """Human-readable action description"""
        action_map = {
            'LOGIN': 'Вход в систему',
            'LOGOUT': 'Выход из системы',
            'REGISTER': 'Регистрация',
            'PROFILE_UPDATE': 'Обновление профиля',
            'PASSWORD_CHANGE': 'Смена пароля',
            'ORDER_CREATE': 'Создание заказа',
            'ORDER_UPDATE': 'Обновление заказа',
            'ORDER_DELETE': 'Удаление заказа',
            'PAYMENT_CREATE': 'Создание платежа',
            'PAYMENT_CONFIRM': 'Подтверждение платежа',
            'PAYMENT_VOID': 'Отмена платежа',
            'PAYMENT_REFUND': 'Возврат платежа',
            'XML_UPLOAD': 'Загрузка XML файла',
            'USER_CREATE': 'Создание пользователя',
            'USER_UPDATE': 'Обновление пользователя',
            'USER_DELETE': 'Удаление пользователя',
            'EVENT_CREATE': 'Создание турнира',
            'EVENT_UPDATE': 'Обновление турнира',
            'EVENT_DELETE': 'Удаление турнира',
            'TELEGRAM_ORDER': 'Заказ через Telegram',
            'VIDEO_LINKS_SEND': 'Отправка ссылок на видео',
            'SYSTEM_BACKUP': 'Резервное копирование',
            'SYSTEM_MAINTENANCE': 'Техническое обслуживание'
        }
        return action_map.get(self.action, self.action)
    
    @property
    def resource_display(self):
        """Human-readable resource description"""
        if self.resource_type == 'user':
            return f"Пользователь #{self.resource_id}"
        elif self.resource_type == 'order':
            return f"Заказ #{self.resource_id}"
        elif self.resource_type == 'payment':
            return f"Платеж #{self.resource_id}"
        elif self.resource_type == 'event':
            return f"Турнир #{self.resource_id}"
        elif self.resource_type == 'category':
            return f"Категория #{self.resource_id}"
        elif self.resource_type == 'athlete':
            return f"Спортсмен #{self.resource_id}"
        elif self.resource_type == 'telegram':
            return f"Telegram пользователь #{self.resource_id}"
        else:
            return f"{self.resource_type or 'Система'}"
    
    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user_id}>'

class SystemSetting(db.Model):
    """System settings model"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SystemSetting {self.key}>'

class OrderChat(db.Model):
    """Chat room for order communication between operator and mom"""
    __tablename__ = 'order_chats'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    order = db.relationship('Order', backref='chat', uselist=False)
    messages = db.relationship('ChatMessage', backref='chat', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_unread_count_for_user(self, user_id):
        """Get unread message count for specific user"""
        return self.messages.filter(
            ChatMessage.sender_id != user_id,
            ChatMessage.is_read == False
        ).count()
    
    def mark_messages_as_read(self, user_id):
        """Mark all messages as read for specific user"""
        self.messages.filter(
            ChatMessage.sender_id != user_id,
            ChatMessage.is_read == False
        ).update({'is_read': True})
        db.session.commit()
    
    def __repr__(self):
        return f'<OrderChat {self.order_id}>'

class ChatMessage(db.Model):
    """Individual chat messages"""
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('order_chats.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.Enum('user', 'system', name='message_type'), default='user')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # File attachment (optional)
    attachment_path = db.Column(db.String(500), nullable=True)
    attachment_name = db.Column(db.String(255), nullable=True)
    
    # Relationships
    sender = db.relationship('User', backref='sent_messages')
    
    def __repr__(self):
        return f'<ChatMessage {self.id}: {self.message[:50]}...>'

# User loader for Flask-Login
from app import login_manager

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
