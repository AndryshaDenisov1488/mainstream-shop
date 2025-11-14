from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db, limiter
from app.auth import bp
from app.auth.forms import (LoginForm, RegistrationForm, PasswordResetForm, 
                           PasswordResetConfirmForm, ChangePasswordForm)
from app.models import User, AuditLog
from app.utils.decorators import role_required
from app.utils.email import send_password_reset_email, send_user_credentials_email, send_new_password_email

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # ✅ Максимум 5 попыток входа в минуту
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        login_field = form.login_field.data.strip()
        
        # Determine if it's email or phone and search accordingly
        user = None
        login_method = None
        
        if '@' in login_field:
            # Search by email
            user = User.query.filter_by(email=login_field.lower()).first()
            login_method = 'email'
        else:
            # Search by phone
            try:
                import phonenumbers
                parsed_phone = phonenumbers.parse(login_field, "RU")
                if phonenumbers.is_valid_number(parsed_phone):
                    formatted_phone = phonenumbers.format_number(parsed_phone, phonenumbers.PhoneNumberFormat.E164)
                    user = User.query.filter_by(phone=formatted_phone).first()
                    login_method = 'phone'
                else:
                    flash('Некорректный номер телефона', 'error')
                    return render_template('auth/login.html', form=form)
            except Exception as e:
                # Если не удалось распарсить телефон, пытаемся найти по исходному значению
                user = User.query.filter_by(phone=login_field).first()
                if not user:
                    flash('Некорректный формат email или номера телефона', 'error')
                    return render_template('auth/login.html', form=form)
                login_method = 'phone'
        
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Ваш аккаунт деактивирован. Обратитесь к администратору.', 'error')
                return render_template('auth/login.html', form=form)
            
            login_user(user, remember=form.remember_me.data)
            
            # Update last login
            from app.utils.datetime_utils import moscow_now_naive
            user.last_login = moscow_now_naive()
            db.session.commit()
            
            # Redirect to appropriate dashboard
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                if user.role == 'ADMIN':
                    next_page = url_for('admin.dashboard')
                elif user.role == 'MOM':
                    next_page = url_for('mom.dashboard')
                elif user.role == 'OPERATOR':
                    next_page = url_for('operator.dashboard')
                elif user.role == 'CUSTOMER':
                    next_page = url_for('customer.dashboard')
                else:
                    next_page = url_for('main.index')
            
            # Log successful login
            AuditLog.log_user_action(
                user_id=user.id,
                action='LOGIN',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                details={'remember_me': form.remember_me.data}
            )
            
            flash(f'Добро пожаловать, {user.full_name}!', 'success')
            return redirect(next_page)
        else:
            if user:
                # Пользователь найден, но пароль неверный
                flash('Неверный пароль', 'error')
            else:
                # Пользователь не найден
                if login_method == 'email':
                    flash('Пользователь с таким email не найден', 'error')
                elif login_method == 'phone':
                    flash('Пользователь с таким номером телефона не найден', 'error')
                else:
                    flash('Неверный email/телефон или пароль', 'error')
    
    return render_template('auth/login.html', form=form)

@bp.route('/logout')
@login_required
def logout():
    # Log logout
    AuditLog.log_user_action(
        user_id=current_user.id,
        action='LOGOUT',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    logout_user()
    flash('Вы успешно вышли из системы', 'info')
    return redirect(url_for('main.index'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data.lower(),
            full_name=form.full_name.data,
            phone=form.phone.data,
            role='CUSTOMER'
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        # Log registration
        AuditLog.create_log(
            user_id=user.id,
            action='REGISTER',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        flash('Регистрация прошла успешно! Теперь вы можете войти в систему.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', form=form)

@bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = PasswordResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            # Generate new password
            new_password = User.generate_password()
            user.set_password(new_password)
            db.session.commit()
            
            # Send new password via email
            send_new_password_email(user, new_password)
            
            # Log password reset
            AuditLog.create_log(
                user_id=user.id,
                action='PASSWORD_RESET',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            flash('Новый пароль отправлен на ваш email', 'success')
        else:
            flash('Пользователь с таким email не найден', 'error')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', form=form)

@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_confirm(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    user = User.verify_reset_password_token(token)
    if not user:
        flash('Недействительная или истекшая ссылка для сброса пароля', 'error')
        return redirect(url_for('auth.reset_password'))
    
    form = PasswordResetConfirmForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        
        # Log password reset
        AuditLog.create_log(
            user_id=user.id,
            action='PASSWORD_RESET',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        flash('Пароль успешно изменен', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password_confirm.html', form=form)

@bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Неверный текущий пароль', 'error')
            return render_template('auth/change_password.html', form=form)
        
        current_user.set_password(form.new_password.data)
        db.session.commit()
        
        # Log password change
        AuditLog.create_log(
            user_id=current_user.id,
            action='PASSWORD_CHANGE',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        flash('Пароль успешно изменен', 'success')
        return redirect(url_for('main.index'))
    
    return render_template('auth/change_password.html', form=form)
