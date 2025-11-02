from flask import Blueprint

bp = Blueprint('mom', __name__)

from app.mom import routes