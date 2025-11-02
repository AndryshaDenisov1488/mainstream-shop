from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional
from app.models import User

class CreateUserForm(FlaskForm):
    """Form for creating new users"""
    full_name = StringField('Полное имя', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Телефон', validators=[Optional()])
    role = SelectField('Роль', choices=[
        ('CUSTOMER', 'Клиент'),
        ('OPERATOR', 'Оператор'),
        ('MOM', 'МОМ'),
        ('ADMIN', 'Администратор')
    ], validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[
        DataRequired(), 
        Length(min=6, max=100),
        EqualTo('confirm_password', message='Пароли должны совпадать')
    ])
    confirm_password = PasswordField('Подтвердите пароль', validators=[DataRequired()])
    is_active = BooleanField('Активный', default=True)
    submit = SubmitField('Создать пользователя')

class EditUserForm(FlaskForm):
    """Form for editing users"""
    full_name = StringField('Полное имя', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Телефон', validators=[Optional()])
    role = SelectField('Роль', choices=[
        ('CUSTOMER', 'Клиент'),
        ('OPERATOR', 'Оператор'),
        ('MOM', 'МОМ'),
        ('ADMIN', 'Администратор')
    ], validators=[DataRequired()])
    is_active = BooleanField('Активный')
    submit = SubmitField('Сохранить изменения')
    generate_password = SubmitField('Сгенерировать новый пароль')

