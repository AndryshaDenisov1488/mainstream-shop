#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WSGI конфигурация для MainStream Shop с платежами
"""

import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

# Создаем приложение
application = create_app()

if __name__ == "__main__":
    application.run()