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

def init_scheduler(app):
    """Initialize APScheduler with background tasks"""
    
    # Configure job stores and executors
    jobstores = {
        'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
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
    
    # Add jobs
    with app.app_context():
        # Cancel expired orders every minute
        scheduler.add_job(
            func='app.tasks.order_cleanup:cancel_expired_orders',
            trigger=IntervalTrigger(minutes=1),
            id='cancel_expired_orders',
            name='Cancel expired orders',
            replace_existing=True
        )
        
        # Clean up old audit logs daily at 3 AM
        scheduler.add_job(
            func='app.tasks.order_cleanup:cleanup_old_audit_logs',
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
