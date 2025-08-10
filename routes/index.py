# .\routes\index.py

from flask import Blueprint, render_template
from module_logger import get_module_logger # <-- 导入

index_bp = Blueprint('index', __name__)
logger = get_module_logger('index_routes') # <-- 初始化

@index_bp.route('/')
def index():
    logger.info("Main index page accessed.") # <-- 添加日志
    return render_template('index.html')