"""
Admin audit panel for tracking all system actions
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import desc, and_, or_
from datetime import datetime, timedelta
from app.utils.datetime_utils import moscow_now_naive
from app.models import AuditLog, User, Order, Payment
from app import db
from app.utils.decorators import role_required
import json

audit_bp = Blueprint('audit', __name__, url_prefix='/admin/audit')

@audit_bp.route('/')
@login_required
@role_required('ADMIN')
def dashboard():
    """Main audit dashboard"""
    # Get filter parameters
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user', '')
    resource_filter = request.args.get('resource', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    
    # Build query
    query = AuditLog.query
    
    # Apply filters
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    
    if user_filter:
        query = query.filter(
            or_(
                AuditLog.user_id == user_filter,
                AuditLog.resource_id == user_filter
            )
        )
    
    if resource_filter:
        query = query.filter(AuditLog.resource_type.ilike(f'%{resource_filter}%'))
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at <= date_to_obj)
        except ValueError:
            pass
    
    # Get paginated results
    logs = query.order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get statistics
    stats = get_audit_statistics()
    
    return render_template('admin/audit/dashboard.html',
                         logs=logs,
                         stats=stats,
                         action_filter=action_filter,
                         user_filter=user_filter,
                         resource_filter=resource_filter,
                         date_from=date_from,
                         date_to=date_to)

@audit_bp.route('/user/<int:user_id>')
@login_required
@role_required('ADMIN')
def user_activity(user_id):
    """User activity audit"""
    user = User.query.get_or_404(user_id)
    page = request.args.get('page', 1, type=int)
    
    # Get user's audit logs
    logs = AuditLog.query.filter(
        or_(
            AuditLog.user_id == user_id,
            AuditLog.resource_id == str(user_id)
        )
    ).order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get user statistics
    user_stats = get_user_audit_statistics(user_id)
    
    return render_template('admin/audit/user_activity.html',
                         user=user,
                         logs=logs,
                         stats=user_stats)

@audit_bp.route('/orders')
@login_required
@role_required('ADMIN')
def orders_audit():
    """Orders audit"""
    page = request.args.get('page', 1, type=int)
    
    # Get order-related audit logs
    # Учитываем оба варианта: 'order' и 'Order' (разные части кода используют разные варианты)
    # Также учитываем действия, связанные с заказами
    logs = AuditLog.query.filter(
        or_(
            AuditLog.resource_type.in_(['order', 'Order']),
            AuditLog.action.ilike('%ORDER_%'),
            AuditLog.action.in_(['LINKS_SENT', 'MOM_CAPTURED_PARTIAL', 'MOM_CAPTURED_FULL', 
                                'MOM_CAPTURED_SBP', 'MOM_REFUNDED_FULL', 'MOM_REFUNDED_PARTIAL',
                                'MOM_CONFIRMED_RECEIPT', 'OPERATOR_TOOK_ORDER', 'ORDER_COMMENTS_UPDATE',
                                'ORDER_REFUND', 'ORDER_CANCELLED_MANUAL', 'ORDER_AUTO_CANCELLED_TIMEOUT'])
        )
    ).order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('admin/audit/orders_audit.html', logs=logs)

@audit_bp.route('/payments')
@login_required
@role_required('ADMIN')
def payments_audit():
    """Payments audit"""
    page = request.args.get('page', 1, type=int)
    
    # Get payment-related audit logs
    logs = AuditLog.query.filter(
        or_(
            AuditLog.resource_type == 'payment',
            AuditLog.action.ilike('%PAYMENT_%')
        )
    ).order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('admin/audit/payments_audit.html', logs=logs)

@audit_bp.route('/telegram')
@login_required
@role_required('ADMIN')
def telegram_audit():
    """Telegram bot audit"""
    page = request.args.get('page', 1, type=int)
    
    # Get Telegram-related audit logs
    logs = AuditLog.query.filter(
        or_(
            AuditLog.resource_type == 'telegram',
            AuditLog.action.ilike('TELEGRAM_%')
        )
    ).order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('admin/audit/telegram_audit.html', logs=logs)

@audit_bp.route('/system')
@login_required
@role_required('ADMIN')
def system_audit():
    """System audit"""
    page = request.args.get('page', 1, type=int)
    
    # Get system-related audit logs
    logs = AuditLog.query.filter(
        AuditLog.action.ilike('SYSTEM_%')
    ).order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('admin/audit/system_audit.html', logs=logs)

@audit_bp.route('/export')
@login_required
@role_required('ADMIN')
def export_audit():
    """Export audit logs to CSV"""
    from flask import make_response
    import csv
    import io
    
    # Get filter parameters
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user', '')
    resource_filter = request.args.get('resource', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = AuditLog.query
    
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    
    if user_filter:
        query = query.filter(
            or_(
                AuditLog.user_id == user_filter,
                AuditLog.resource_id == user_filter
            )
        )
    
    if resource_filter:
        query = query.filter(AuditLog.resource_type.ilike(f'%{resource_filter}%'))
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at <= date_to_obj)
        except ValueError:
            pass
    
    # Get all logs (no pagination for export)
    logs = query.order_by(desc(AuditLog.created_at)).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'ID', 'Дата/Время', 'Пользователь', 'Действие', 
        'Тип ресурса', 'ID ресурса', 'IP адрес', 'Детали'
    ])
    
    # Write data
    for log in logs:
        user_info = f"{log.user.full_name} ({log.user.email})" if log.user else "Система"
        details = json.dumps(log.details, ensure_ascii=False) if log.details else ""
        
        writer.writerow([
            log.id,
            log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            user_info,
            log.action_display,
            log.resource_type or '',
            log.resource_id or '',
            log.ip_address or '',
            details
        ])
    
    # Create response
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=audit_logs_{moscow_now_naive().strftime("%Y%m%d_%H%M%S")}.csv'
    
    return response

@audit_bp.route('/stats')
@login_required
@role_required('ADMIN')
def get_stats():
    """Get audit statistics as JSON"""
    stats = get_audit_statistics()
    return jsonify(stats)

def get_audit_statistics():
    """Get audit statistics"""
    now = moscow_now_naive()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    stats = {
        'total_logs': AuditLog.query.count(),
        'today_logs': AuditLog.query.filter(
            AuditLog.created_at >= today
        ).count(),
        'week_logs': AuditLog.query.filter(
            AuditLog.created_at >= week_ago
        ).count(),
        'month_logs': AuditLog.query.filter(
            AuditLog.created_at >= month_ago
        ).count(),
        'unique_users_today': AuditLog.query.filter(
            AuditLog.created_at >= today,
            AuditLog.user_id.isnot(None)
        ).distinct(AuditLog.user_id).count(),
        'unique_users_week': AuditLog.query.filter(
            AuditLog.created_at >= week_ago,
            AuditLog.user_id.isnot(None)
        ).distinct(AuditLog.user_id).count(),
        'top_actions': db.session.query(
            AuditLog.action, db.func.count(AuditLog.id)
        ).group_by(AuditLog.action).order_by(
            db.func.count(AuditLog.id).desc()
        ).limit(10).all(),
        'top_users': db.session.query(
            AuditLog.user_id, User.full_name, db.func.count(AuditLog.id)
        ).join(User).group_by(
            AuditLog.user_id, User.full_name
        ).order_by(
            db.func.count(AuditLog.id).desc()
        ).limit(10).all()
    }
    
    return stats

def get_user_audit_statistics(user_id):
    """Get user-specific audit statistics"""
    now = moscow_now_naive()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    user_query = AuditLog.query.filter(
        or_(
            AuditLog.user_id == user_id,
            AuditLog.resource_id == str(user_id)
        )
    )
    
    stats = {
        'total_actions': user_query.count(),
        'today_actions': user_query.filter(
            AuditLog.created_at >= today
        ).count(),
        'week_actions': user_query.filter(
            AuditLog.created_at >= week_ago
        ).count(),
        'month_actions': user_query.filter(
            AuditLog.created_at >= month_ago
        ).count(),
        'action_breakdown': db.session.query(
            AuditLog.action, db.func.count(AuditLog.id)
        ).filter(
            or_(
                AuditLog.user_id == user_id,
                AuditLog.resource_id == str(user_id)
            )
        ).group_by(AuditLog.action).order_by(
            db.func.count(AuditLog.id).desc()
        ).all(),
        'last_login': user_query.filter(
            AuditLog.action == 'LOGIN'
        ).order_by(desc(AuditLog.created_at)).first(),
        'last_activity': user_query.order_by(desc(AuditLog.created_at)).first()
    }
    
    return stats
