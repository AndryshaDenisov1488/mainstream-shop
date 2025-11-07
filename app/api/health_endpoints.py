"""
Health Check Endpoints
Provides system health monitoring
"""

from flask import jsonify, current_app
from app import db
from app.utils.datetime_utils import moscow_now_naive
import logging

logger = logging.getLogger(__name__)

def register_health_routes(bp):
    """Register health check routes"""
    
    @bp.route('/health', methods=['GET'])
    def health_check():
        """
        ✅ Health check endpoint for monitoring
        
        Returns system health status and checks for:
        - Database connectivity
        - CloudPayments API configuration
        - Telegram bot configuration
        - Email server configuration
        """
        checks = {
            'database': check_database(),
            'cloudpayments': check_cloudpayments(),
            'telegram': check_telegram(),
            'email': check_email()
        }
        
        all_healthy = all(checks.values())
        status_code = 200 if all_healthy else 503
        
        return jsonify({
            'status': 'healthy' if all_healthy else 'unhealthy',
            'checks': checks,
            'timestamp': moscow_now_naive().isoformat(),
            'version': '1.0.0'
        }), status_code
    
    @bp.route('/health/database', methods=['GET'])
    def health_database():
        """Check database health"""
        healthy = check_database()
        return jsonify({
            'database': healthy,
            'timestamp': moscow_now_naive().isoformat()
        }), 200 if healthy else 503


def check_database():
    """Check database connectivity"""
    try:
        # Simple query to check database is accessible
        db.session.execute('SELECT 1')
        return True
    except Exception as e:
        logger.error(f'Database health check failed: {str(e)}')
        return False


def check_cloudpayments():
    """Check CloudPayments configuration"""
    try:
        public_id = current_app.config.get('CLOUDPAYMENTS_PUBLIC_ID')
        api_secret = current_app.config.get('CLOUDPAYMENTS_API_SECRET')
        
        if not public_id or not api_secret:
            logger.warning('CloudPayments credentials not configured')
            return False
        
        # Проверяем что credentials не пустые и не дефолтные
        if public_id == 'your_public_id' or api_secret == 'your_api_secret':
            logger.warning('CloudPayments credentials are default values')
            return False
        
        return True
    except Exception as e:
        logger.error(f'CloudPayments health check failed: {str(e)}')
        return False


def check_telegram():
    """Check Telegram bot configuration"""
    try:
        token = current_app.config.get('TELEGRAM_BOT_TOKEN')
        
        if not token:
            logger.warning('Telegram bot token not configured')
            return False
        
        # Проверяем что токен не дефолтный
        if token == 'your_telegram_bot_token':
            logger.warning('Telegram bot token is default value')
            return False
        
        return True
    except Exception as e:
        logger.error(f'Telegram health check failed: {str(e)}')
        return False


def check_email():
    """Check email server configuration"""
    try:
        mail_server = current_app.config.get('MAIL_SERVER')
        mail_username = current_app.config.get('MAIL_USERNAME')
        mail_password = current_app.config.get('MAIL_PASSWORD')
        
        if not mail_server or not mail_username:
            logger.warning('Email server not configured')
            return False
        
        # В production должен быть пароль
        if current_app.config.get('FLASK_ENV') == 'production' and not mail_password:
            logger.warning('Email password not configured in production')
            return False
        
        return True
    except Exception as e:
        logger.error(f'Email health check failed: {str(e)}')
        return False

