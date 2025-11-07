from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.admin import bp
from app.models import User, Event, Category, Athlete, Order, Payment, AuditLog, SystemSetting, VideoType
from app.utils.decorators import admin_required, admin_or_mom_required
from app.utils.email import send_user_credentials_email
from app.admin.forms import CreateUserForm, EditUserForm
from sqlalchemy import desc, func
from werkzeug.utils import secure_filename
import os
# ✅ Используем defusedxml для защиты от XXE атак
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
    import warnings
    warnings.warn("defusedxml not installed - XXE protection disabled", UserWarning)
from datetime import datetime, timedelta
from app.utils.datetime_utils import moscow_now_naive

@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with statistics"""
    
    # Get statistics
    stats = {
        'total_users': User.query.count(),
        'total_orders': Order.query.count(),
        'total_events': Event.query.count(),
        'total_revenue': db.session.query(func.sum(Payment.amount)).filter(
            Payment.status == 'confirmed'
        ).scalar() or 0,
        'pending_orders': Order.query.filter(Order.status.in_(['checkout_initiated', 'awaiting_payment'])).count(),
        'processing_orders': Order.query.filter_by(status='processing').count(),
        'completed_orders': Order.query.filter_by(status='completed').count(),
        'cancelled_orders': Order.query.filter(Order.status.in_(['cancelled_unpaid', 'cancelled_manual'])).count(),
    }
    
    # Recent orders
    recent_orders = Order.query.order_by(desc(Order.created_at)).limit(10).all()
    
    # Recent users
    recent_users = User.query.order_by(desc(User.created_at)).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_orders=recent_orders,
                         recent_users=recent_users)

@bp.route('/users')
@login_required
@admin_required
def users():
    """User management page"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    role_filter = request.args.get('role', '', type=str)
    
    query = User.query
    
    if search:
        query = query.filter(
            (User.full_name.contains(search)) |
            (User.email.contains(search))
        )
    
    if role_filter:
        query = query.filter(User.role == role_filter)
    
    users = query.order_by(desc(User.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/users.html', users=users, search=search, role_filter=role_filter)

@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    """Create new user"""
    if request.method == 'POST':
        try:
            # Get form data
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            role = request.form.get('role')
            password = request.form.get('password')
            is_active = bool(request.form.get('is_active'))
            send_email = bool(request.form.get('send_email'))
            
            # Validate required fields
            if not all([full_name, email, role]):
                flash('Заполните все обязательные поля', 'error')
                return render_template('admin/create_user.html')
            
            # Check if email already exists
            if User.query.filter_by(email=email.lower()).first():
                flash('Пользователь с таким email уже существует', 'error')
                return render_template('admin/create_user.html')
            
            # Create user
            user = User(
                full_name=full_name,
                email=email.lower(),
                phone=phone,
                role=role,
                is_active=is_active
            )
            
            # Set password
            if password:
                user.set_password(password)
            else:
                # Generate random password
                password = User.generate_password()
                user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Send credentials email if requested
            if send_email:
                send_user_credentials_email(user, password)
            
            # Log action
            AuditLog.log_admin_action(
                user_id=current_user.id,
                action='USER_CREATE',
                resource_type='User',
                resource_id=user.id,
                details=f'Created user: {user.email} with role {user.role.value}',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            flash('Пользователь успешно создан', 'success')
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error creating user: {str(e)}')
            flash('Ошибка при создании пользователя', 'error')
    
    return render_template('admin/create_user.html')

@bp.route('/users/<int:user_id>/toggle-status')
@login_required
@admin_required
def toggle_user_status(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Нельзя изменить статус собственного аккаунта', 'error')
        return redirect(url_for('admin.users'))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    # Log action
    AuditLog.log_admin_action(
        user_id=current_user.id,
        action='USER_TOGGLE_STATUS',
        resource_type='User',
        resource_id=user.id,
        details=f'Toggled user {user.email} status to {"active" if user.is_active else "inactive"}',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    status_text = 'активирован' if user.is_active else 'заблокирован'
    flash(f'Пользователь {status_text}', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.email = request.form.get('email')
        user.phone = request.form.get('phone')
        user.role = request.form.get('role')
        user.is_active = bool(request.form.get('is_active'))
        
        # Generate new password if requested
        if request.form.get('generate_password'):
            new_password = User.generate_password()
            user.set_password(new_password)
            send_user_credentials_email(user, new_password)
            flash('Новый пароль отправлен на email пользователя', 'success')
        
        db.session.commit()
        
        # Log action
        AuditLog.log_admin_action(
            user_id=current_user.id,
            action='USER_UPDATE',
            resource_type='User',
            resource_id=user.id,
            details=f'Updated user {user.email} fields: {", ".join(request.form.keys())}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        flash('Пользователь успешно обновлен', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', user=user)

@bp.route('/events')
@login_required
@admin_or_mom_required
def events():
    """Events management page"""
    page = request.args.get('page', 1, type=int)
    events = Event.query.order_by(desc(Event.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get statistics for each event
    event_stats = {}
    for event in events.items:
        orders = Order.query.filter_by(event_id=event.id).all()
        event_stats[event.id] = {
            'total_orders': len(orders),
            'pending_orders': len([o for o in orders if o.status in ['checkout_initiated', 'awaiting_payment']]),
            'processing_orders': len([o for o in orders if o.status == 'processing']),
            'completed_orders': len([o for o in orders if o.status == 'completed']),
            'cancelled_orders': len([o for o in orders if o.status in ['cancelled_unpaid', 'cancelled_manual']]),
            'refund_required_orders': len([o for o in orders if o.status == 'refund_required']),
            'total_revenue': sum(float(o.total_amount) for o in orders if o.status == 'completed'),
            'refund_reasons': {}
        }
        
        # Get refund reasons
        refund_orders = [o for o in orders if o.status == 'refund_required' or o.status in ['cancelled_unpaid', 'cancelled_manual']]
        for order in refund_orders:
            if order.operator_comment:
                reason = order.operator_comment[:50] + '...' if len(order.operator_comment) > 50 else order.operator_comment
                event_stats[event.id]['refund_reasons'][reason] = event_stats[event.id]['refund_reasons'].get(reason, 0) + 1
    
    return render_template('admin/events.html', events=events, event_stats=event_stats)

@bp.route('/customers')
@login_required
@admin_or_mom_required
def customers():
    """Super informative customers page"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    sort_by = request.args.get('sort', 'created_at', type=str)
    sort_order = request.args.get('order', 'desc', type=str)
    
    # Build query - показываем только пользователей с ролью CUSTOMER
    query = User.query.filter(User.role == 'CUSTOMER')
    
    # Search functionality
    if search:
        query = query.filter(
            (User.full_name.contains(search)) |
            (User.email.contains(search)) |
            (User.phone.contains(search))
        )
    
    # Sorting
    if sort_by == 'name':
        query = query.order_by(User.full_name.asc() if sort_order == 'asc' else User.full_name.desc())
    elif sort_by == 'email':
        query = query.order_by(User.email.asc() if sort_order == 'asc' else User.email.desc())
    elif sort_by == 'orders':
        # This will be handled after pagination
        query = query.order_by(User.created_at.desc())
    else:  # created_at
        query = query.order_by(User.created_at.asc() if sort_order == 'asc' else User.created_at.desc())
    
    # Paginate
    customers_paginated = query.paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get detailed statistics for each customer
    customer_stats = {}
    for customer in customers_paginated.items:
        orders = Order.query.filter_by(customer_id=customer.id).all()
        
        # Calculate statistics
        total_orders = len(orders)
        completed_orders = len([o for o in orders if o.status == 'completed'])
        total_spent = sum(o.total_amount for o in orders if o.status == 'completed')
        
        # Get events and video types
        events_participated = set()
        video_types_ordered = set()
        children_data = set()  # Collect unique children data
        
        for order in orders:
            if order.event:
                events_participated.add(order.event.name)
            if order.video_types:
                for vt_id in order.video_types:
                    vt = VideoType.query.get(vt_id)
                    if vt:
                        video_types_ordered.add(vt.name)
            
            # Collect children data - use athlete data as child data
            if order.athlete:
                child_info = {
                    'name': order.athlete.name,
                    'birth_date': order.child_birth_date.strftime('%d.%m.%Y') if order.child_birth_date else None,
                    'gender': order.child_gender,
                    'team': order.child_team or order.athlete.team if hasattr(order.athlete, 'team') else None,
                    'coach': order.child_coach or order.athlete.coach if hasattr(order.athlete, 'coach') else None
                }
                children_data.add(tuple(child_info.items()))
        
        # Get last order date
        last_order = Order.query.filter_by(customer_id=customer.id).order_by(Order.created_at.desc()).first()
        
        # Get order status breakdown
        status_breakdown = {}
        for order in orders:
            status_breakdown[order.status] = status_breakdown.get(order.status, 0) + 1
        
        customer_stats[customer.id] = {
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'total_spent': total_spent,
            'events_participated': list(events_participated),
            'video_types_ordered': list(video_types_ordered),
            'children_data': [dict(child) for child in children_data],
            'last_order_date': last_order.created_at if last_order else None,
            'status_breakdown': status_breakdown,
            'average_order_value': total_spent / completed_orders if completed_orders > 0 else 0
        }
    
    return render_template('admin/customers.html', 
                         customers=customers_paginated, 
                         customer_stats=customer_stats,
                         search=search, sort_by=sort_by, sort_order=sort_order)

@bp.route('/events/<int:event_id>/toggle-status')
@login_required
@admin_or_mom_required
def toggle_event_status(event_id):
    """Toggle event active status"""
    event = Event.query.get_or_404(event_id)
    
    event.is_active = not event.is_active
    db.session.commit()
    
    # Log action
    AuditLog.log_admin_action(
        user_id=current_user.id,
        action='EVENT_TOGGLE_STATUS',
        resource_type='Event',
        resource_id=event.id,
        details=f'Toggled event {event.name} status to {"active" if event.is_active else "inactive"}',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    status_text = 'активирован' if event.is_active else 'деактивирован'
    flash(f'Турнир {status_text}', 'success')
    return redirect(url_for('admin.events'))

@bp.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_or_mom_required
def edit_event(event_id):
    """Edit event"""
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'POST':
        try:
            event.name = request.form.get('name', event.name)
            event.place = request.form.get('place', event.place)
            event.description = request.form.get('description', event.description)
            
            # Parse dates
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            
            if start_date_str:
                try:
                    event.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            if end_date_str:
                try:
                    event.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            event.is_active = 'is_active' in request.form
            
            db.session.commit()
            
            # Log action
            AuditLog.log_admin_action(
                user_id=current_user.id,
                action='EVENT_UPDATE',
                resource_type='Event',
                resource_id=event.id,
                details=f'Updated event: {event.name}',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            flash('Турнир успешно обновлен', 'success')
            return redirect(url_for('admin.events'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Event update error: {str(e)}')
            flash(f'Ошибка при обновлении турнира: {str(e)}', 'error')
    
    return render_template('admin/edit_event.html', event=event)

@bp.route('/events/upload', methods=['GET', 'POST'])
@bp.route('/upload-xml', methods=['GET', 'POST'])
@login_required
@admin_required
def upload_xml():
    """Upload XML file with tournament data"""
    if request.method == 'POST':
        if 'xml_file' not in request.files:
            flash('Файл не выбран', 'error')
            return render_template('admin/upload_xml.html')
        
        file = request.files['xml_file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return render_template('admin/upload_xml.html')
        
        if file and file.filename.lower().endswith('.xml'):
            try:
                # Save file temporarily
                filename = secure_filename(file.filename)
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Parse XML and create records
                event = parse_xml_file(filepath)
                
                # Handle auto_activate if requested
                if request.form.get('auto_activate'):
                    event.is_active = True
                    db.session.commit()
                
                # Log action
                AuditLog.log_admin_action(
                    user_id=current_user.id,
                    action='XML_UPLOAD',
                    resource_type='Event',
                    resource_id=event.id,
                    details=f'Uploaded XML: {file.filename}',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                
                flash(f'XML файл успешно загружен! Создан турнир: {event.name}', 'success')
                
                # Clean up temp file
                os.remove(filepath)
                
                return redirect(url_for('admin.events'))
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f'XML upload error: {str(e)}')
                flash(f'Ошибка при обработке XML файла: {str(e)}', 'error')
        else:
            flash('Выберите XML файл', 'error')
    
    return render_template('admin/upload_xml.html')

def parse_xml_file(filepath):
    """Parse XML file and create database records"""
    tree = ET.parse(filepath)
    root = tree.getroot()
    
    # Find Event element
    event_elem = root.find('Event')
    if event_elem is None:
        raise ValueError('Event element not found in XML')
    
    # Extract event data from attributes
    event_name = event_elem.get('EVT_NAME', 'Unknown')
    event_place = event_elem.get('EVT_PLACE', None)
    event_start = event_elem.get('EVT_BEGDAT', None)
    event_end = event_elem.get('EVT_ENDDAT', None)
    
    # Parse dates
    start_date = None
    end_date = None
    if event_start:
        try:
            start_date = datetime.strptime(event_start, '%Y%m%d').date()
        except ValueError:
            pass
    
    if event_end:
        try:
            end_date = datetime.strptime(event_end, '%Y%m%d').date()
        except ValueError:
            pass
    
    # Check if event already exists
    existing_event = Event.query.filter_by(
        name=event_name,
        start_date=start_date
    ).first()
    
    if existing_event:
        raise ValueError(f'Турнир "{event_name}" с датой {start_date} уже существует')
    
    # Create event
    event = Event(
        name=event_name,
        place=event_place,
        start_date=start_date,
        end_date=end_date
    )
    db.session.add(event)
    db.session.flush()  # Get event ID
    
    counts = {'categories': 0, 'athletes': 0}
    
    # Find Categories_List and process categories
    categories_list = event_elem.find('Categories_List')
    if categories_list is not None:
        for category_elem in categories_list.findall('Category'):
            # Extract category data from attributes
            category_name = category_elem.get('CAT_NAME', 'Unknown')
            category_gender = category_elem.get('CAT_GENDER', None)
            
            # Normalize gender
            gender = None
            if category_gender:
                if category_gender.upper() in ['M', 'MALE', 'М', 'МУЖ']:
                    gender = 'M'
                elif category_gender.upper() in ['F', 'FEMALE', 'Ж', 'ЖЕН']:
                    gender = 'F'
                else:
                    gender = 'MIXED'
            
            category = Category(
                name=category_name,
                gender=gender,
                event_id=event.id
            )
            db.session.add(category)
            db.session.flush()  # Get category ID
            counts['categories'] += 1
            
            # Process athletes in this category
            # Look for participants in segments
            segments_list = category_elem.find('Segments_List')
            if segments_list is not None:
                for segment in segments_list.findall('Segment'):
                    # Look for participants in this segment
                    participants_list = segment.find('Participants_List')
                    if participants_list is not None:
                        for participant_elem in participants_list.findall('Participant'):
                            # Get person data
                            person_elem = participant_elem.find('Person_Couple_Team')
                            if person_elem is None:
                                continue
                            
                            # Extract athlete data from attributes
                            athlete_name = person_elem.get('PCT_CNAME', 'Unknown')
                            athlete_birth = person_elem.get('PCT_BDAY', None)
                            athlete_gender = person_elem.get('PCT_GENDER', None)
                            
                            # Parse birth date
                            birth_date = None
                            if athlete_birth:
                                try:
                                    birth_date = datetime.strptime(athlete_birth, '%Y%m%d').date()
                                except ValueError:
                                    pass
                            
                            # Normalize athlete gender
                            athlete_gender_normalized = None
                            if athlete_gender:
                                if athlete_gender.upper() in ['M', 'MALE', 'М', 'МУЖ']:
                                    athlete_gender_normalized = 'M'
                                elif athlete_gender.upper() in ['F', 'FEMALE', 'Ж', 'ЖЕН']:
                                    athlete_gender_normalized = 'F'
                            
                            # Get club name
                            club_elem = person_elem.find('Club')
                            club_name = None
                            if club_elem is not None:
                                club_name = club_elem.get('CLB_NAME', None)
                            
                            # Handle pairs (simplified - would need more complex logic for real implementation)
                            is_pair = '/' in athlete_name
                            partner_name = None
                            if is_pair:
                                # Extract partner name from pair notation
                                names = athlete_name.split(' / ')
                                if len(names) >= 2:
                                    athlete_name = names[0].strip()
                                    partner_name = names[1].strip()
                            
                            athlete = Athlete(
                                name=athlete_name,
                                birth_date=birth_date,
                                gender=athlete_gender_normalized,
                                club_name=club_name,
                                category_id=category.id,
                                is_pair=is_pair,
                                partner_name=partner_name
                            )
                            db.session.add(athlete)
                            counts['athletes'] += 1
    
    db.session.commit()
    
    return event

@bp.route('/orders')
@login_required
@admin_or_mom_required
def orders():
    """Orders management page"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    search = request.args.get('search', '', type=str)
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    
    query = Order.query
    
    if status_filter:
        query = query.filter(Order.status == status_filter)
    
    if search:
        query = query.filter(
            (Order.generated_order_number.contains(search)) |
            (Order.contact_email.contains(search)) |
            (Order.contact_first_name.contains(search)) |
            (Order.contact_last_name.contains(search))
        )
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(func.date(Order.created_at) >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(func.date(Order.created_at) <= date_to_obj)
        except ValueError:
            pass
    
    orders = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    return render_template('admin/orders.html', orders=orders, status_filter=status_filter, search=search, date_from=date_from, date_to=date_to, video_types_dict=video_types_dict)

@bp.route('/orders/<int:order_id>')
@login_required
@admin_or_mom_required
def order_detail(order_id):
    """Order detail page"""
    order = Order.query.get_or_404(order_id)
    
    # Get video types for display
    video_types = VideoType.query.all()
    video_types_dict = {str(vt.id): vt for vt in video_types}
    
    return render_template('admin/order_detail.html', order=order, video_types_dict=video_types_dict)

@bp.route('/analytics')
@login_required
@admin_required
def analytics():
    """Analytics page"""
    
    # Revenue by month (last 12 months) - SQLite compatible
    revenue_data = db.session.query(
        func.strftime('%Y-%m', Order.created_at).label('month'),
        func.sum(Payment.amount).label('revenue')
    ).join(Payment).filter(
        Payment.status == 'confirmed'
    ).group_by('month').order_by('month').limit(12).all()
    
    # Orders by status
    orders_by_status = db.session.query(
        Order.status,
        func.count(Order.id).label('count')
    ).group_by(Order.status).all()
    
    # Top events by orders
    top_events = db.session.query(
        Event.name,
        func.count(Order.id).label('orders_count')
    ).join(Order).group_by(Event.id, Event.name).order_by(
        func.count(Order.id).desc()
    ).limit(10).all()
    
    return render_template('admin/analytics.html',
                         revenue_data=revenue_data,
                         orders_by_status=orders_by_status,
                         top_events=top_events)

@bp.route('/customer/<int:customer_id>/details')
@login_required
@admin_required
def customer_details(customer_id):
    """Get detailed customer information"""
    try:
        # Показываем только клиентов с ролью CUSTOMER
        customer = User.query.filter_by(id=customer_id, role='CUSTOMER').first_or_404()
        
        # Get all orders for this customer
        orders = Order.query.filter_by(customer_id=customer_id).order_by(Order.created_at.desc()).all()
        
        # Get statistics
        total_orders = len(orders)
        completed_orders = len([o for o in orders if o.status == 'completed'])
        total_spent = sum(o.total_amount for o in orders if o.status == 'completed')
        
        # Get events participated
        events = set()
        for order in orders:
            if order.event:
                events.add(order.event.name)
        
        # Get video types ordered
        video_types = set()
        for order in orders:
            if order.video_types:
                for vt_id in order.video_types:
                    vt = VideoType.query.get(vt_id)
                    if vt:
                        video_types.add(vt.name)
        
        # Get children data - use athlete data as child data
        children_data = set()
        for order in orders:
            if order.athlete:
                child_info = {
                    'name': order.athlete.name,
                    'birth_date': order.child_birth_date.strftime('%d.%m.%Y') if order.child_birth_date else None,
                    'gender': order.child_gender,
                    'team': order.child_team or (order.athlete.team if hasattr(order.athlete, 'team') else None),
                    'coach': order.child_coach or (order.athlete.coach if hasattr(order.athlete, 'coach') else None)
                }
                children_data.add(tuple(child_info.items()))
        
        return jsonify({
            'success': True,
            'customer': {
                'id': customer.id,
                'full_name': customer.full_name,
                'email': customer.email,
                'phone': customer.phone,
                'created_at': customer.created_at.isoformat() if customer.created_at else None,
                'is_active': customer.is_active
            },
            'statistics': {
                'total_orders': total_orders,
                'completed_orders': completed_orders,
                'total_spent': float(total_spent),
                'events_participated': list(events),
                'video_types_ordered': list(video_types),
                'children_data': [dict(child) for child in children_data]
            },
            'orders': [{
                'id': order.id,
                'generated_order_number': order.generated_order_number,
                'status': order.status,
                'total_amount': float(order.total_amount),
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'event_name': order.event.name if order.event else 'Не указан',
                'athlete_name': order.athlete.name if order.athlete else 'Не указан'
            } for order in orders]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/finance')
@login_required
@admin_required
def finance():
    """Finance dashboard with advanced analytics"""
    from datetime import datetime, timedelta
    from sqlalchemy import func, extract, case
    
    # Get filter parameters
    period = request.args.get('period', 'month', type=str)  # day, week, month, year
    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)
    
    # Set default date range
    if not start_date or not end_date:
        now = moscow_now_naive()
        if period == 'day':
            end_date = now.strftime('%Y-%m-%d')
            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
        elif period == 'week':
            end_date = now.strftime('%Y-%m-%d')
            start_date = (now - timedelta(days=90)).strftime('%Y-%m-%d')
        elif period == 'month':
            end_date = now.strftime('%Y-%m-%d')
            start_date = (now - timedelta(days=365)).strftime('%Y-%m-%d')
        else:  # year
            end_date = now.strftime('%Y-%m-%d')
            start_date = (now - timedelta(days=1095)).strftime('%Y-%m-%d')
    
    # Convert to datetime objects
    # start_dt - начало дня (00:00:00)
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    # end_dt - конец дня (23:59:59), чтобы включить все заказы за этот день
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    # Base query for orders in date range
    base_query = Order.query.filter(
        Order.created_at >= start_dt,
        Order.created_at <= end_dt
    )
    
    # Revenue analytics - SQLite compatible date functions
    if period == 'day':
        date_trunc = func.date(Order.created_at)
    elif period == 'week':
        # SQLite doesn't have date_trunc, use strftime for week
        date_trunc = func.strftime('%Y-%W', Order.created_at)
    elif period == 'month':
        # SQLite compatible month grouping
        date_trunc = func.strftime('%Y-%m', Order.created_at)
    else:  # year
        # SQLite compatible year grouping
        date_trunc = func.strftime('%Y', Order.created_at)
    
    # Revenue by period - учитываем заказы где деньги приняты (completed, links_sent, completed_partial_refund)
    # Для completed_partial_refund используем paid_amount, для остальных - total_amount
    revenue_by_period = db.session.query(
        date_trunc.label('period'),
        func.sum(
            case(
                (Order.status == 'completed_partial_refund', Order.paid_amount or 0),
                (Order.status.in_(['completed', 'links_sent']), Order.total_amount),
                else_=0
            )
        ).label('revenue'),
        func.count(Order.id).label('total_orders'),
        func.count(case((Order.status.in_(['completed', 'links_sent', 'completed_partial_refund']), 1), else_=None)).label('completed_orders'),
        func.count(case((Order.status.in_(['cancelled_unpaid', 'cancelled_manual']), 1), else_=None)).label('cancelled_orders'),
        func.count(case((Order.status == 'refund_required', 1), else_=None)).label('refund_orders')
    ).filter(
        Order.created_at >= start_dt,
        Order.created_at <= end_dt
    ).group_by('period').order_by('period').all()
    
    # Payment analytics
    payment_stats = db.session.query(
        Payment.status,
        func.count(Payment.id).label('count'),
        func.sum(Payment.amount).label('total_amount')
    ).join(Order).filter(
        Order.created_at >= start_dt,
        Order.created_at <= end_dt
    ).group_by(Payment.status).all()
    
    # Video type analytics
    video_type_stats = []
    for vt in VideoType.query.filter_by(is_active=True).all():
        orders_count = base_query.filter(
            Order.video_types.contains([vt.id])
        ).count()
        
        revenue = db.session.query(
            func.sum(
                case(
                    (Order.status == 'completed_partial_refund', Order.paid_amount or 0),
                    (Order.status.in_(['completed', 'links_sent']), Order.total_amount),
                    else_=0
                )
            )
        ).filter(
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
            Order.video_types.contains([vt.id])
        ).scalar() or 0
        
        video_type_stats.append({
            'video_type': vt,
            'orders_count': orders_count,
            'revenue': float(revenue),
            'average_order_value': float(revenue / orders_count) if orders_count > 0 else 0
        })
    
    # Event analytics
    event_stats = []
    for event in Event.query.all():
        event_orders = base_query.filter_by(event_id=event.id)
        orders_count = event_orders.count()
        
        revenue = db.session.query(
            func.sum(
                case(
                    (Order.status == 'completed_partial_refund', Order.paid_amount or 0),
                    (Order.status.in_(['completed', 'links_sent']), Order.total_amount),
                    else_=0
                )
            )
        ).filter(
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
            Order.event_id == event.id
        ).scalar() or 0
        
        event_stats.append({
            'event': event,
            'orders_count': orders_count,
            'revenue': float(revenue),
            'average_order_value': float(revenue / orders_count) if orders_count > 0 else 0
        })
    
    # Overall statistics - учитываем заказы где деньги приняты
    # Для completed_partial_refund используем paid_amount, для остальных - total_amount
    total_revenue = db.session.query(
        func.sum(
            case(
                (Order.status == 'completed_partial_refund', Order.paid_amount or 0),
                (Order.status.in_(['completed', 'links_sent']), Order.total_amount),
                else_=0
            )
        )
    ).filter(
        Order.created_at >= start_dt,
        Order.created_at <= end_dt
    ).scalar() or 0
    
    # Convert to float if Decimal
    if total_revenue is None:
        total_revenue = 0
    else:
        total_revenue = float(total_revenue)
    
    # Calculate tax (6%) and profit
    tax_rate = 0.06  # 6%
    total_tax = total_revenue * tax_rate
    total_profit = total_revenue - total_tax
    
    total_orders = base_query.count()
    completed_orders = base_query.filter(Order.status.in_(['completed', 'links_sent', 'completed_partial_refund'])).count()
    cancelled_orders = base_query.filter(Order.status.in_(['cancelled_unpaid', 'cancelled_manual'])).count()
    refund_orders = base_query.filter_by(status='refund_required').count()
    
    # Refund analytics
    refund_amount = db.session.query(
        func.sum(case((Order.status == 'refund_required', Order.total_amount), else_=0))
    ).filter(
        Order.created_at >= start_dt,
        Order.created_at <= end_dt
    ).scalar() or 0
    
    # Customer analytics
    new_customers = User.query.filter(
        User.role == 'CUSTOMER',
        User.created_at >= start_dt,
        User.created_at <= end_dt
    ).count()
    
    active_customers = db.session.query(func.count(func.distinct(Order.customer_id))).filter(
        Order.created_at >= start_dt,
        Order.created_at <= end_dt
    ).scalar() or 0
    
    return render_template('admin/finance.html',
                         period=period,
                         start_date=start_date,
                         end_date=end_date,
                         revenue_by_period=revenue_by_period,
                         payment_stats=payment_stats,
                         video_type_stats=video_type_stats,
                         event_stats=event_stats,
                         total_revenue=total_revenue,
                         total_tax=total_tax,
                         total_profit=total_profit,
                         total_orders=total_orders,
                         completed_orders=completed_orders,
                         cancelled_orders=cancelled_orders,
                         refund_orders=refund_orders,
                         refund_amount=float(refund_amount),
                         new_customers=new_customers,
                         active_customers=active_customers)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """System settings page"""
    
    # Handle POST request for updating settings
    if request.method == 'POST':
        try:
            price_changes = []
            settings_changes = []
            
            # Handle video type price updates
            video_types = VideoType.query.filter_by(is_active=True).all()
            for video_type in video_types:
                new_price = request.form.get(f'price_{video_type.id}')
                if new_price:
                    try:
                        new_price_float = float(new_price)
                        if new_price_float != float(video_type.price):
                            old_price = float(video_type.price)
                            video_type.price = new_price_float
                            price_changes.append({
                                'video_type_id': video_type.id,
                                'video_type_name': video_type.name,
                                'old_price': old_price,
                                'new_price': new_price_float
                            })
                    except ValueError:
                        flash(f'Некорректная цена для {video_type.name}', 'error')
                        continue
            
            # Handle general settings
            settings = SystemSetting.query.all()
            for setting in settings:
                new_value = request.form.get(f'setting_{setting.key}')
                if new_value is not None and new_value != setting.value:
                    old_value = setting.value
                    setting.value = new_value
                    settings_changes.append({
                        'key': setting.key,
                        'name': setting.description or setting.key,
                        'old_value': old_value,
                        'new_value': new_value
                    })
            
            db.session.commit()
            
            # Log price changes
            if price_changes:
                for change in price_changes:
                    AuditLog.log_admin_action(
                        user_id=current_user.id,
                        action='PRICE_UPDATE',
                        resource_type='VideoType',
                        resource_id=str(change['video_type_id']),
                        details={
                            'video_type_name': change['video_type_name'],
                            'old_price': change['old_price'],
                            'new_price': change['new_price']
                        },
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get('User-Agent')
                    )
            
            # Log settings changes
            if settings_changes:
                for change in settings_changes:
                    AuditLog.log_admin_action(
                        user_id=current_user.id,
                        action='SETTINGS_UPDATE',
                        resource_type='SystemSetting',
                        resource_id=change['key'],
                        details={
                            'setting_name': change['name'],
                            'old_value': change['old_value'],
                            'new_value': change['new_value']
                        },
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get('User-Agent')
                    )
            
            # Invalidate settings cache after update
            from app.utils.settings import invalidate_cache
            invalidate_cache()
            
            flash('Настройки сохранены', 'success')
            return redirect(url_for('admin.settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении настроек: {e}', 'error')
            return redirect(url_for('admin.settings'))
    
    # Get video types for price management
    video_types = VideoType.query.filter_by(is_active=True).all()
    
    # Get general settings
    settings = SystemSetting.query.all()
    
    # Get counts for dashboard
    users_count = User.query.filter_by(role='CUSTOMER').count()
    orders_count = Order.query.count()
    events_count = Event.query.count()
    video_types_count = VideoType.query.filter_by(is_active=True).count()
    
    return render_template('admin/settings.html', 
                         settings=settings, 
                         video_types=video_types,
                         users_count=users_count,
                         orders_count=orders_count,
                         events_count=events_count,
                         video_types_count=video_types_count)

@bp.route('/settings/download-db')
@login_required
@admin_required
def download_database():
    """Download database backup"""
    import shutil
    from flask import send_file
    import os
    
    try:
        from flask import current_app
        
        # Get database path - handle different SQLite URI formats
        db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri.replace('sqlite:///', '')
        elif db_uri.startswith('sqlite://'):
            db_path = db_uri.replace('sqlite://', '')
        else:
            db_path = db_uri
        
        # Make path absolute if it's relative
        if not os.path.isabs(db_path):
            db_path = os.path.join(current_app.instance_path, db_path)
        
        if not os.path.exists(db_path):
            flash(f'База данных не найдена: {db_path}', 'error')
            return redirect(url_for('admin.settings'))
        
        # Create backup filename with timestamp
        timestamp = moscow_now_naive().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'database_backup_{timestamp}.db'
        backup_path = os.path.join(current_app.instance_path, backup_filename)
        
        # Copy database file
        shutil.copy2(db_path, backup_path)
        
        # Log backup action
        AuditLog.log_admin_action(
            user_id=current_user.id,
            action='SYSTEM_BACKUP',
            resource_type='Database',
            resource_id=backup_filename,
            details={
                'backup_filename': backup_filename,
                'db_path': db_path
            },
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        # Send file to user
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/x-sqlite3'
        )
        
    except Exception as e:
        flash(f'Ошибка при создании резервной копии: {str(e)}', 'error')
        return redirect(url_for('admin.settings'))

@bp.route('/audit_log')
@login_required
@admin_required
def audit_log():
    """Audit log page"""
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '', type=str)
    
    query = AuditLog.query
    
    if action_filter:
        query = query.filter(AuditLog.action.contains(action_filter))
    
    logs = query.order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('admin/audit_log.html', logs=logs, action_filter=action_filter)
