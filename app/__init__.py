from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
import os
import logging

logger = logging.getLogger(__name__)

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'
    login_manager.login_message_category = 'info'
    
    # Create upload directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['XML_UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from app.main import bp as main_bp
    from app.auth import bp as auth_bp
    from app.admin import bp as admin_bp
    from app.admin.audit import audit_bp
    from app.customer import bp as customer_bp
    from app.mom import bp as mom_bp
    from app.operator import bp as operator_bp
    from app.api import bp as api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(audit_bp, url_prefix='/admin/audit')
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(operator_bp, url_prefix='/operator')
    app.register_blueprint(mom_bp, url_prefix='/mom')
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Initialize background tasks (skip if creating database)
    # Skip initialization only if explicitly requested or during database creation
    should_skip_background = os.environ.get('SKIP_BACKGROUND_TASKS', 'false').lower() == 'true'
    logger.info(f"DEBUG: should_skip_background={should_skip_background}")
    print(f"DEBUG: should_skip_background={should_skip_background}", flush=True)
    
    if not should_skip_background:
        logger.info("DEBUG: Entering background tasks initialization")
        print("DEBUG: Entering background tasks initialization", flush=True)
        # Initialize scheduler
        if not os.environ.get('SKIP_SCHEDULER'):
            try:
                from app.tasks.scheduler import init_scheduler
                init_scheduler(app)
                logger.info("✅ Scheduler initialized")
            except Exception as e:
                # Если БД еще не создана, scheduler не критичен
                if 'unable to open database file' not in str(e) and 'no such table' not in str(e).lower():
                    logger.error(f"Scheduler initialization error: {e}", exc_info=True)
        
        # Initialize Telegram bot
        if not os.environ.get('SKIP_TELEGRAM_BOT'):
            try:
                logger.info("DEBUG: Starting Telegram bot initialization...")
                print("DEBUG: Starting Telegram bot initialization...", flush=True)
                from app.telegram_bot.runner import initialize_bot
                bot_thread = initialize_bot(app)
                logger.info(f"DEBUG: initialize_bot returned: {bot_thread}")
                print(f"DEBUG: initialize_bot returned: {bot_thread}", flush=True)
                if bot_thread:
                    logger.info("✅ Telegram bot initialization started")
                    print("✅ Telegram bot initialization started", flush=True)
                else:
                    logger.warning("⚠️ Telegram bot initialization returned None (token may be missing)")
                    print("⚠️ Telegram bot initialization returned None (token may be missing)", flush=True)
            except Exception as e:
                # Если БД еще не создана или токен не настроен, бот не критичен
                logger.error(f"DEBUG: Exception in bot initialization: {e}", exc_info=True)
                print(f"DEBUG: Exception in bot initialization: {e}", flush=True)
                if 'unable to open database file' not in str(e) and 'no such table' not in str(e).lower():
                    logger.warning(f"Telegram bot initialization skipped: {e}")
                    print(f"Telegram bot initialization skipped: {e}", flush=True)
                else:
                    logger.warning(f"Telegram bot initialization skipped (DB not ready): {e}")
                    print(f"Telegram bot initialization skipped (DB not ready): {e}", flush=True)
    else:
        logger.info("⚠️ Background tasks (scheduler, bot) skipped due to SKIP_BACKGROUND_TASKS flag")
        print("⚠️ Background tasks (scheduler, bot) skipped due to SKIP_BACKGROUND_TASKS flag", flush=True)
    
    # Add context processor for settings (available in all templates)
    @app.context_processor
    def inject_settings():
        try:
            from app.utils.settings import (
                get_contact_email, get_telegram_bot_username, get_whatsapp_number,
                get_site_name, get_site_description, get_video_link_expiry_days
            )
            return {
                'contact_email': get_contact_email(),
                'telegram_bot_username': get_telegram_bot_username(),
                'whatsapp_number': get_whatsapp_number(),
                'site_name': get_site_name(),
                'site_description': get_site_description(),
                'video_link_expiry_days': get_video_link_expiry_days(),
            }
        except Exception as e:
            logger.error(f"Error injecting settings into template context: {e}")
            return {
                'contact_email': 'support@mainstreamfs.ru',
                'telegram_bot_username': '@mainstreamshopbot',
                'whatsapp_number': '+7 (999) 123-45-67',
                'site_name': 'MainStream Shop',
                'site_description': 'Профессиональные видео с турниров по фигурному катанию',
                'video_link_expiry_days': 90,
            }
    
    return app

from app import models
