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
    
    if not should_skip_background:
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
                from app.telegram_bot.runner import initialize_bot
                bot_thread = initialize_bot(app)
                if bot_thread:
                    logger.info("✅ Telegram bot initialization started")
                else:
                    logger.warning("⚠️ Telegram bot initialization returned None (token may be missing)")
            except Exception as e:
                # Если БД еще не создана или токен не настроен, бот не критичен
                if 'unable to open database file' not in str(e) and 'no such table' not in str(e).lower():
                    logger.warning(f"Telegram bot initialization skipped: {e}")
                else:
                    logger.debug(f"Telegram bot initialization skipped (DB not ready): {e}")
    else:
        logger.info("⚠️ Background tasks (scheduler, bot) skipped due to SKIP_BACKGROUND_TASKS flag")
    
    return app

from app import models
