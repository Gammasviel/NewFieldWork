# .\routes\index.py

from flask import Blueprint, render_template
import logging # <-- 导入

index_bp = Blueprint('index', __name__)
logger = logging.getLogger('index_routes') # <-- 初始化

@index_bp.route('/dev')
@index_bp.route('/dev/index')
def index():
    logger.info("Main index page accessed.") # <-- 添加日志
    return render_template('index.html')