import os
import secrets
import logging
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))
logger = logging.getLogger(__name__)

class Config:
    # Basic Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        if os.environ.get('FLASK_ENV') == 'production':
            raise ValueError("SECRET_KEY environment variable is REQUIRED in production!")
        else:
            # Only for development, generate random
            SECRET_KEY = secrets.token_hex(32)
            logger.warning('⚠️  Using auto-generated SECRET_KEY for development. Set SECRET_KEY env var for production!')
    
    # Session Configuration
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ['true', 'on', '1']
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Database Configuration
    # Use absolute path for SQLite on Windows to avoid path issues
    if os.environ.get('DATABASE_URL'):
        db_url = os.environ.get('DATABASE_URL')
        # If it's already a full path, use it as is
        # Otherwise, convert relative path to absolute
        if db_url.startswith('sqlite:///'):
            # Extract path from sqlite:///path
            path_part = db_url[10:]  # Remove 'sqlite:///'
            if not os.path.isabs(path_part):
                # Relative path - make it absolute
                path_part = os.path.abspath(os.path.join(basedir, path_part))
            # Ensure directory exists
            instance_dir = os.path.dirname(path_part)
            if not os.path.exists(instance_dir):
                os.makedirs(instance_dir)
            SQLALCHEMY_DATABASE_URI = 'sqlite:///' + path_part.replace('\\', '/')
        else:
            SQLALCHEMY_DATABASE_URI = db_url
    else:
        db_path = os.path.join(basedir, 'instance', 'app.db')
        # Ensure instance directory exists
        instance_dir = os.path.dirname(db_path)
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir)
        # Convert Windows path to SQLite URI format
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.abspath(db_path).replace('\\', '/')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload Configuration
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    XML_UPLOAD_FOLDER = os.path.join(basedir, 'uploads', 'xml')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    MAX_CHAT_FILE_SIZE = 10 * 1024 * 1024  # 10MB max for chat attachments
    
    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.beget.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 465)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'false').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'orders@mainstreamfs.ru'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    if not MAIL_PASSWORD and os.environ.get('FLASK_ENV') == 'production':
        raise ValueError("MAIL_PASSWORD environment variable is required in production!")
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'orders@mainstreamfs.ru'
    
    # Payment Configuration (CloudPayments)
    CLOUDPAYMENTS_PUBLIC_ID = os.environ.get('CLOUDPAYMENTS_PUBLIC_ID')
    CLOUDPAYMENTS_API_SECRET = os.environ.get('CLOUDPAYMENTS_API_SECRET')
    if not CLOUDPAYMENTS_PUBLIC_ID or not CLOUDPAYMENTS_API_SECRET:
        if os.environ.get('FLASK_ENV') == 'production':
            raise ValueError("CloudPayments credentials must be set via environment variables in production!")
        else:
            logger.warning('⚠️  CloudPayments credentials not set. Payment functionality will not work.')
    CLOUDPAYMENTS_CURRENCY = 'RUB'
    CLOUDPAYMENTS_TEST_MODE = os.environ.get('CLOUDPAYMENTS_TEST_MODE', 'False').lower() == 'true'
    CLOUDPAYMENTS_WEBHOOK_URL = os.environ.get('CLOUDPAYMENTS_WEBHOOK_URL') or 'https://mainstreamfs.ru/api/cloudpayments/webhook'
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not TELEGRAM_BOT_TOKEN and os.environ.get('FLASK_ENV') == 'production':
        logger.warning('⚠️  TELEGRAM_BOT_TOKEN not set. Telegram bot functionality will not work.')
    TELEGRAM_WEBHOOK_URL = os.environ.get('TELEGRAM_WEBHOOK_URL')
    
    # Application Configuration
    PER_PAGE = 20
    VIDEO_LINK_EXPIRY_DAYS = 90
    PAYMENT_CONFIRMATION_DAYS = 7
    
    # Flask-Limiter Configuration
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL') or os.environ.get('REDIS_URL') or 'memory://'
    
    # Test mode - allows payments without user registration
    TEST_MODE = os.environ.get('TEST_MODE', 'True').lower() == 'true'
    
    # Security Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SSL_STRICT = os.environ.get('WTF_CSRF_SSL_STRICT', 'false').lower() in ['true', 'on', '1']
    
    # Disable CSP for CloudPayments testing
    CSP_ENABLED = False
    
    # Logging
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT')

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app_dev.db')

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app_prod.db')
    
    # Beget server specific settings
    SERVER_NAME = os.environ.get('SERVER_NAME') or 'mainstreamfs.ru'
    PREFERRED_URL_SCHEME = 'https'
    
    # Security settings for production
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() in ['true', 'on', '1']
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SSL_STRICT = os.environ.get('WTF_CSRF_SSL_STRICT', 'true').lower() in ['true', 'on', '1']

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
