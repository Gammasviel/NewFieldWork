from flask import Flask
from flask_migrate import Migrate
from models import db, Setting, LLM
from llm import clients
from config import DEFAULT_CRITERIA
from routes import dimensions_bp, index_bp, leaderboard_bp, models_bp, questions_bp, settings_bp
from module_logger import get_module_logger

# from import_llms import import_datas
import_datas = lambda x:x

logger = get_module_logger('flask_app')

def create_app():
    logger.info("Flask app creation started.")
    app = Flask(__name__)
    app.config.from_pyfile('config.py')
    
    logger.info("Initializing database.")
    db.init_app(app)
    
    migrate = Migrate(app, db)
    
    logger.info("Registering blueprints.")
    app.register_blueprint(dimensions_bp)
    app.register_blueprint(index_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(questions_bp)
    app.register_blueprint(settings_bp)
    
    with app.app_context():
        logger.info("Creating all database tables.")
        db.create_all()
        import_datas(app)
        
        all_llms = LLM.query.all()
        logger.info(f"Creating LLM clients for {len(all_llms)} models.")
        clients.create_clients([
            {
                'id': llm.id,
                'name': llm.name,
                'model': llm.model,
                'base_url': llm.base_url,
                'api_keys': llm.api_keys,
                'proxy': llm.proxy
            }
            for llm in all_llms
        ])
        
        if Setting.query.first() is None:
            logger.info("No settings found. Creating default settings.")
            default_setting_objective = Setting(question_type = 'objective', criteria=DEFAULT_CRITERIA['objective'])
            default_setting_subjective = Setting(question_type = 'subjective', criteria=DEFAULT_CRITERIA['subjective'])
            db.session.add(default_setting_objective)
            db.session.add(default_setting_subjective)
            db.session.commit()
            logger.info("Default settings created successfully.")
            
    logger.info("Flask app creation finished.")
    return app


if __name__ == '__main__':
    app = create_app()
    logger.info("Starting Flask development server.")
    app.run(debug=True)