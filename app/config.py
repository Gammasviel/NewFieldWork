import os
from pathlib import Path

SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
SQLALCHEMY_DATABASE_URI = 'sqlite:///evaluation.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False

CELERY = {
    'broker_url': 'redis://localhost:6379/0',
    'result_backend': 'redis://localhost:6379/0'
}

UPLOADED_ICONS_DEST = 'static/uploads/icons'

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / 'instance'
EXPORTS_DIR = INSTANCE_DIR / 'exports'
EXPORTS_IMGS_DIR = EXPORTS_DIR / 'imgs'
EXPORTS_REPORTS_DIR = EXPORTS_DIR / 'reports'