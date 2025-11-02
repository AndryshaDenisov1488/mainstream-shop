from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.customer import bp
from app.models import Order, Payment, VideoType
from app.utils.decorators import customer_required
from sqlalchemy import desc
from datetime import datetime, timedelta

@bp.route('/dashboard')
@login_required
@customer_required
def dashboard():
    """Customer dashboard"""
    
    # Get user's orders
    orders = Order.query.filter_by(customer_id=current_user.id)\
                       .order_by(desc(Order.created_at)).limit(10).all()
    
    # Get statistics
    stats = {
        'pending_orders': Order.query.filter(
            Order.customer_id == current_user.id,
            Order.status.in_(['pending_payment', 'pending'])
        ).count(),
        'processing_orders': Order.query.filter(
            Order.customer_id == current_user.id,
            Order.status.in_(['processing', 'awaiting_info', 'links_sent'])
        ).count(),
    }
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types} if video_types else {}
    
    return render_template('customer/dashboard.html', orders=orders, stats=stats, video_types_dict=video_types_dict)

@bp.route('/orders')
@login_required
@customer_required
def orders():
    """Customer orders page"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    
    query = Order.query.filter_by(customer_id=current_user.id)
    
    if status_filter:
        query = query.filter(Order.status == status_filter)
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=10, error_out=False
    )
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types} if video_types else {}
    
    return render_template('customer/orders.html', orders=orders, status_filter=status_filter, video_types_dict=video_types_dict)

@bp.route('/order/<int:order_id>')
@login_required
@customer_required
def order_detail(order_id):
    """Order detail page"""
    # Find order by customer_id OR by contact_email (for guest users)
    order = Order.query.filter(
        (Order.id == order_id) & 
        ((Order.customer_id == current_user.id) | (Order.contact_email == current_user.email))
    ).first_or_404()
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types} if video_types else {}
    
    return render_template('customer/order_detail.html', order=order, video_types_dict=video_types_dict)

@bp.route('/profile')
@login_required
@customer_required
def profile():
    """Customer profile page"""
    return render_template('customer/profile.html')

@bp.route('/profile/update', methods=['POST'])
@login_required
@customer_required
def update_profile():
    """Update customer profile"""
    current_user.full_name = request.form.get('full_name')
    current_user.phone = request.form.get('phone')
    
    db.session.commit()
    
    flash('Профиль успешно обновлен', 'success')
    return redirect(url_for('customer.profile'))
