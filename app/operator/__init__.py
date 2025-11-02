from flask import Blueprint

bp = Blueprint('operator', __name__)

from app.operator import routes