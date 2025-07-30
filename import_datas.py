from models import db, Question


def import_datas(app):
    with app.app_context():
        pass
        db.session.commit()