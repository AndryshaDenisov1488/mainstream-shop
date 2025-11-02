from functools import wraps
from flask import abort, request
from flask_login import current_user

def role_required(*roles):
    """Decorator to require specific user roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return abort(403)
            if current_user.role not in roles:
                return abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator to require admin role"""
    return role_required('ADMIN')(f)

def mom_required(f):
    """Decorator to require mom role"""
    return role_required('MOM')(f)

def operator_required(f):
    """Decorator to require operator role"""
    return role_required('OPERATOR')(f)

def customer_required(f):
    """Decorator to require customer role"""
    return role_required('CUSTOMER')(f)

def admin_or_mom_required(f):
    """Decorator to require admin or mom role"""
    return role_required('ADMIN', 'MOM')(f)

def admin_or_operator_required(f):
    """Decorator to require admin or operator role"""
    return role_required('ADMIN', 'OPERATOR')(f)

def staff_required(f):
    """Decorator to require staff role (admin, mom, or operator)"""
    return role_required('ADMIN', 'MOM', 'OPERATOR')(f)
