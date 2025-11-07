from flask import Blueprint

bp = Blueprint('api', __name__)

from app.api import routes
from app.api.refund_endpoints import register_refund_routes
from app.api.payment_confirmation_endpoints import register_payment_confirmation_routes
from app.api.health_endpoints import register_health_routes
from app.api.chat_endpoints import bp as chat_bp
from app.api.chat_export_endpoints import bp as chat_export_bp

# Register refund routes
register_refund_routes(bp)

# Register payment confirmation routes
register_payment_confirmation_routes(bp)

# Register health check routes
register_health_routes(bp)

# Register chat routes
bp.register_blueprint(chat_bp)

# Register chat export routes
bp.register_blueprint(chat_export_bp)
