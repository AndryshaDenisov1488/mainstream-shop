#!/usr/bin/env python3
"""
MainStream Shop - Main Application Runner
"""

import os
import sys
from app import create_app, db
from app.models import User, Event, Category, Athlete, VideoType, SystemSetting
from flask_migrate import upgrade

def create_default_data():
    """Create default system data"""
    
    # Create default video types
    if VideoType.query.count() == 0:
        sport_video = VideoType(
            name='Спорт версия',
            description='Профессиональная съемка с фокусом на технику выполнения элементов',
            price=1500.00
        )
        
        tv_video = VideoType(
            name='ТВ версия', 
            description='Телевизионная версия с комментариями и графикой',
            price=2000.00
        )
        
        db.session.add(sport_video)
        db.session.add(tv_video)
        db.session.commit()
        print("✅ Created default video types")
    
    # Create default admin user
    if User.query.filter_by(role='ADMIN').count() == 0:
        admin = User(
            email='admin@mainstreamfs.ru',
            full_name='Администратор',
            phone='+7 (000) 000-00-00',
            role='ADMIN'
        )
        admin.set_password('admin123')  # Change in production!
        
        db.session.add(admin)
        db.session.commit()
        print("✅ Created default admin user (admin@mainstreamfs.ru / admin123)")
    
    # Create default mom user
    if User.query.filter_by(role='MOM').count() == 0:
        mom = User(
            email='mom@mainstreamshop.ru',
            full_name='Финансовый контролер',
            phone='+7 (000) 000-00-01',
            role='MOM'
        )
        mom.set_password('mom123')  # Change in production!
        
        db.session.add(mom)
        db.session.commit()
        print("✅ Created default mom user (mom@mainstreamshop.ru / mom123)")
    
    # Create default operator user
    if User.query.filter_by(role='OPERATOR').count() == 0:
        operator = User(
            email='operator@mainstreamshop.ru',
            full_name='Оператор',
            phone='+7 (000) 000-00-02',
            role='OPERATOR'
        )
        operator.set_password('operator123')  # Change in production!
        
        db.session.add(operator)
        db.session.commit()
        print("✅ Created default operator user (operator@mainstreamshop.ru / operator123)")
    
    # Create default system settings
    if SystemSetting.query.count() == 0:
        settings = [
            SystemSetting(key='site_name', value='MainStream Shop', description='Название сайта'),
            SystemSetting(key='site_description', value='Профессиональные видео с турниров по фигурному катанию', description='Описание сайта'),
            SystemSetting(key='contact_email', value='noreply@mainstreamshop.ru', description='Email для связи'),
            SystemSetting(key='video_link_expiry_days', value='90', description='Срок действия ссылок на видео (дни)'),
            SystemSetting(key='order_processing_days', value='4', description='Срок обработки заказов (дни)'),
            SystemSetting(key='payment_confirmation_days', value='7', description='Срок подтверждения платежей (дни)'),
        ]
        
        for setting in settings:
            db.session.add(setting)
        
        db.session.commit()
        print("✅ Created default system settings")

def main():
    """Main application entry point"""
    
    # Ensure instance directory exists
    import os
    instance_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    if not os.path.exists(instance_dir):
        os.makedirs(instance_dir)
        print(f"✅ Created instance directory: {instance_dir}")
    
    # Create app
    app = create_app()
    
    with app.app_context():
        # Create database tables (skip if already exists and has tables)
        try:
            # Check if database file exists and has tables
            db_file = os.path.join(instance_dir, 'app.db')
            if os.path.exists(db_file):
                # Try to connect - if it works, tables exist
                try:
                    db.session.execute(db.text('SELECT 1'))
                    print("✅ Database already exists and is accessible")
                except:
                    db.create_all()
                    print("✅ Created database tables")
            else:
                db.create_all()
                print("✅ Created database tables")
        except Exception as e:
            print(f"⚠️ Database creation warning: {e}")
        
        # Run migrations
        try:
            upgrade()
            print("✅ Database migrations completed")
        except Exception as e:
            print(f"⚠️ Migration warning: {e}")
        
        # Create default data
        create_default_data()
    
    # Start application
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"🚀 Starting MainStream Shop on port {port}")
    print(f"🌐 Open http://localhost:{port} in your browser")
    print(f"👤 Admin panel: http://localhost:{port}/admin")
    
    app.run(host='0.0.0.0', port=port, debug=debug)

if __name__ == '__main__':
    main()
