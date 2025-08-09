from flask import Flask
from flask_migrate import Migrate
from models import db, Setting, LLM
from llm import clients
from config import DEFAULT_CRITERIA
from routes import dimensions_bp, index_bp, leaderboard_bp, models_bp, questions_bp, settings_bp

from import_dimensions import import_datas

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('config.py')
    db.init_app(app)
    # migrate = Migrate(app, db)

    migrate = Migrate(app, db)
    
    app.register_blueprint(dimensions_bp)
    app.register_blueprint(index_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(questions_bp)
    app.register_blueprint(settings_bp)
    
    with app.app_context():
        db.create_all()
        
        clients.create_clients([
            {
                'id': llm.id,
                'model': llm.model,
                'base_url': llm.base_url,
                'api_keys': llm.api_keys,
                'proxy': llm.proxy
            }
            for llm in LLM.query.all()
        ])
        
        if Setting.query.first() is None:
            default_setting_objective = Setting(question_type = 'objective', criteria=DEFAULT_CRITERIA['objective'])
            default_setting_subjective = Setting(question_type = 'subjective', criteria=DEFAULT_CRITERIA['subjective'])
            db.session.add(default_setting_objective)
            db.session.add(default_setting_subjective)
            db.session.commit()
        import_datas(app)
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)