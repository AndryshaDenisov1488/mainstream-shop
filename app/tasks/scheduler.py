"""
APScheduler configuration for background tasks
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from flask import current_app

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения app (для scheduler задач)
_app_instance = None

def init_scheduler(app):
    """Initialize APScheduler with background tasks"""
    global _app_instance
    
    # Сохраняем app в глобальной переменной для использования в задачах
    _app_instance = app
    
    # Configure job stores - используем memory store (SQLAlchemy jobstore вызывает проблемы с сериализацией)
    from apscheduler.jobstores.memory import MemoryJobStore
    jobstores = {
        'default': MemoryJobStore()
    }
    
    executors = {
        'default': ThreadPoolExecutor(20),
    }
    
    job_defaults = {
        'coalesce': False,
        'max_instances': 1
    }
    
    # Create scheduler
    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone='Europe/Moscow'
    )
    
    # Add jobs using string references (APScheduler can serialize these)
    # Cancel expired orders every minute
    scheduler.add_job(
        func='app.tasks.order_cleanup:cancel_expired_orders_with_context',
        trigger=IntervalTrigger(minutes=1),
        id='cancel_expired_orders',
        name='Cancel expired orders',
        replace_existing=True
    )
    
    # Clean up old audit logs daily at 3 AM
    scheduler.add_job(
        func='app.tasks.order_cleanup:cleanup_old_audit_logs_with_context',
        trigger=CronTrigger(hour=3, minute=0),
        id='cleanup_old_audit_logs',
        name='Clean up old audit logs',
        replace_existing=True
    )
    
    # Start scheduler
    scheduler.start()
    logger.info('Background scheduler started')
    
    # Store scheduler in app context for shutdown
    app.scheduler = scheduler
    
    # Register shutdown handler
    import atexit
    atexit.register(lambda: scheduler.shutdown())
    
    return scheduler
