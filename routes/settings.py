from flask import url_for, render_template, Blueprint, redirect, request
from models import Setting
from extensions import db
from forms import SettingForm
from config import DEFAULT_CRITERIA
import logging

settings_bp = Blueprint('settings', __name__, url_prefix='/dev/settings')
logger = logging.getLogger('setting_routes')


@settings_bp.route('/', methods=['GET', 'POST'])
def settings():
    objective_setting = Setting.query.filter_by(question_type='objective').first()
    subjective_setting = Setting.query.filter_by(question_type='subjective').first()
    
    form = SettingForm()
    if form.validate_on_submit():
        question_type = form.question_type.data
        logger.info(f"Attempting to update settings for question type: {question_type}.")
        setting = Setting.query.filter_by(question_type=question_type).first()
        if setting:
            setting.criteria = form.criteria.data
            setting.total_score = form.total_score.data
            logger.info(f"Updated existing settings for '{question_type}'.")
        else:
            setting = Setting(
                question_type=question_type,
                criteria=form.criteria.data,
                total_score=form.total_score.data
            )
            db.session.add(setting)
            logger.info(f"Created new settings for '{question_type}'.")
        
        db.session.commit()
        logger.info("Settings update committed to database.")
        return redirect(url_for('settings.settings'))
    
    if request.method == 'GET':
        logger.info("Accessed settings page.")
        form.question_type.data = 'objective'
        objective_criteria = objective_setting.criteria if objective_setting else DEFAULT_CRITERIA['objective']
        objective_total = objective_setting.total_score if objective_setting else 5.0
        form.criteria.data = objective_criteria
        form.total_score.data = objective_total

    objective_criteria = objective_setting.criteria if objective_setting else DEFAULT_CRITERIA['objective']
    subjective_criteria = subjective_setting.criteria if subjective_setting else DEFAULT_CRITERIA['subjective']
    objective_total = objective_setting.total_score if objective_setting else 5.0
    subjective_total = subjective_setting.total_score if subjective_setting else 5.0
    
    return render_template('settings.html', 
                        form=form,
                        objective_criteria=objective_criteria,
                        subjective_criteria=subjective_criteria,
                        objective_total=objective_total,
                        subjective_total=subjective_total)