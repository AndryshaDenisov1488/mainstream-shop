#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конфигурация Gunicorn для MainStream Shop с платежами
"""

import multiprocessing
import os

# Основные настройки - ИСПОЛЬЗУЕМ ПОРТ 5002
bind = f"0.0.0.0:{os.environ.get('PORT', '5002')}"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 120
keepalive = 5

# Логирование
accesslog = 'logs/gunicorn_access.log'
errorlog = 'logs/gunicorn_error.log'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Процессы
daemon = False
pidfile = 'logs/gunicorn.pid'
umask = 0
user = None
group = None
tmp_upload_dir = None

# Безопасность
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Перезагрузка
max_requests = 1000
max_requests_jitter = 50
graceful_timeout = 30
preload_app = True