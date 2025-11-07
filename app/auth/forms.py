from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from app.models import User
import re

try:
    import phonenumbers
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False

def validate_password_strength(form, field):
    """Validate password strength: minimum 8 characters, letters and numbers"""
    password = field.data
    if not password:
        return
    
    # Check minimum length
    if len(password) < 8:
        raise ValidationError('Пароль должен содержать минимум 8 символов')
    
    # Check for letters
    if not re.search(r'[a-zA-Zа-яА-Я]', password):
        raise ValidationError('Пароль должен содержать буквы')
    
    # Check for numbers
    if not re.search(r'\d', password):
        raise ValidationError('Пароль должен содержать цифры')

class LoginForm(FlaskForm):
    login_field = StringField('Email или телефон', validators=[DataRequired()], 
                             render_kw={'placeholder': 'Введите email или номер телефона'})
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')
    
    def validate_login_field(self, field):
        """Validate that login field is either email or phone"""
        if not field.data:
            return
        
        # Check if it looks like an email
        if '@' in field.data:
            # Validate email format
            from wtforms.validators import Email
            email_validator = Email()
            try:
                email_validator(None, field)
            except ValidationError:
                raise ValidationError('Некорректный email адрес')
        else:
            # Validate phone format
            if not PHONENUMBERS_AVAILABLE:
                raise ValidationError('Библиотека phonenumbers не установлена. Установите: pip install phonenumbers')
            try:
                parsed_phone = phonenumbers.parse(field.data, "RU")
                if not phonenumbers.is_valid_number(parsed_phone):
                    raise ValidationError('Некорректный номер телефона')
            except:
                raise ValidationError('Некорректный номер телефона')

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('ФИО', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Телефон', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=8), validate_password_strength])
    password2 = PasswordField('Подтвердите пароль', 
                             validators=[DataRequired(), EqualTo('password', message='Пароли не совпадают')])
    submit = SubmitField('Зарегистрироваться')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower()).first()
        if user:
            raise ValidationError('Пользователь с таким email уже существует')
    
    def validate_phone(self, phone):
        if phone.data:
            try:
                # Parse and validate phone number
                parsed_number = phonenumbers.parse(phone.data, 'RU')
                if not phonenumbers.is_valid_number(parsed_number):
                    raise ValidationError('Неверный формат номера телефона')
                # Normalize phone number
                self.phone.data = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                raise ValidationError('Неверный формат номера телефона')

class PasswordResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Отправить новый пароль')

class PasswordResetConfirmForm(FlaskForm):
    password = PasswordField('Новый пароль', validators=[DataRequired(), Length(min=8), validate_password_strength])
    password2 = PasswordField('Подтвердите пароль', 
                             validators=[DataRequired(), EqualTo('password', message='Пароли не совпадают')])
    submit = SubmitField('Изменить пароль')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Текущий пароль', validators=[DataRequired()])
    new_password = PasswordField('Новый пароль', validators=[DataRequired(), Length(min=8), validate_password_strength])
    new_password2 = PasswordField('Подтвердите новый пароль', 
                                 validators=[DataRequired(), EqualTo('new_password', message='Пароли не совпадают')])
    submit = SubmitField('Изменить пароль')

class UserEditForm(FlaskForm):
    full_name = StringField('ФИО', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Телефон')
    role = SelectField('Роль', choices=[
        ('ADMIN', 'Администратор'),
        ('MOM', 'Финансовый контролер'),
        ('OPERATOR', 'Оператор'),
        ('CUSTOMER', 'Клиент')
    ])
    is_active = BooleanField('Активен')
    submit = SubmitField('Сохранить')
    
    def validate_phone(self, phone):
        if phone.data:
            try:
                parsed_number = phonenumbers.parse(phone.data, 'RU')
                if not phonenumbers.is_valid_number(parsed_number):
                    raise ValidationError('Неверный формат номера телефона')
                self.phone.data = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                raise ValidationError('Неверный формат номера телефона')
