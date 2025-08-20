# .\extensions.py

# 这个文件将作为所有 Flask 扩展的中央注册处。
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_uploads import UploadSet, IMAGES
from flask_wtf.csrf import CSRFProtect

# 1. 在这里实例化所有扩展对象
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
icons = UploadSet('icons', IMAGES)