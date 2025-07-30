from flask import url_for, render_template, Blueprint, redirect
from models import db, Setting
from forms import SettingForm
from config import DEFAULT_CRITERIA

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/', methods=['GET', 'POST'])
def settings():
    # 获取现有的评分标准
    objective_setting = Setting.query.filter_by(question_type='objective').first()
    subjective_setting = Setting.query.filter_by(question_type='subjective').first()
    
    # 处理表单提交
    form = SettingForm()
    if form.validate_on_submit():
        # 更新对应类型的评分标准
        setting = Setting.query.filter_by(question_type=form.question_type.data).first()
        if setting:
            setting.criteria = form.criteria.data
            setting.total_score = form.total_score.data  # 更新总分
        else:
            setting = Setting(
                question_type=form.question_type.data,
                criteria=form.criteria.data,
                total_score=form.total_score.data  # 设置总分
            )
            db.session.add(setting)
        
        db.session.commit()
        return redirect(url_for('settings.settings'))
    
    # 设置表单初始值
    form.question_type.data = 'objective'  # 默认显示客观题
    
    # 获取数据库中的评分标准
    objective_criteria = objective_setting.criteria if objective_setting else DEFAULT_CRITERIA['objective']
    subjective_criteria = subjective_setting.criteria if subjective_setting else DEFAULT_CRITERIA['subjective']
    
    # 获取总分值
    objective_total = objective_setting.total_score if objective_setting else 5.0
    subjective_total = subjective_setting.total_score if subjective_setting else 5.0
    
    # 设置初始值
    form.criteria.data = objective_criteria
    form.total_score.data = objective_total
    
    return render_template('settings.html', 
                        form=form,
                        objective_criteria=objective_criteria,
                        subjective_criteria=subjective_criteria,
                        objective_total=objective_total,
                        subjective_total=subjective_total)