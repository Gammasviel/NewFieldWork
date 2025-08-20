from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField, FieldList, FormField, Form, FloatField
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import DataRequired, Optional, NumberRange

class DimensionForm(FlaskForm):
    level1 = StringField('一级维度', validators=[DataRequired()])
    level2 = StringField('二级维度', validators=[DataRequired()])
    level3 = StringField('三级维度', validators=[DataRequired()])
    submit = SubmitField('添加维度')

class QuestionForm(FlaskForm):
    level1 = SelectField('一级维度', validators=[DataRequired()])
    level2 = SelectField('二级维度', validators=[DataRequired()])
    level3 = SelectField('三级维度', validators=[DataRequired()])
    question_type = SelectField('题目类型', choices=[
        ('subjective', '主观题'),
        ('objective', '客观题')
    ], validators=[DataRequired()])
    content = TextAreaField('问题内容', validators=[DataRequired()])
    answer = TextAreaField('问题答案（仅客观题）')
    submit = SubmitField('添加题目')

# forms.py
class SettingForm(FlaskForm):
    question_type = SelectField('题目类型', choices=[
        ('subjective', '主观题'),
        ('objective', '客观题')
    ], validators=[DataRequired()])
    criteria = TextAreaField('评分标准', validators=[DataRequired()])
    total_score = FloatField('总分值', validators=[  # 新增字段
        DataRequired(),
        NumberRange(min=1, max=100, message="总分值必须在1到100之间")
    ])
    submit = SubmitField('更新评分标准')
    
class APIKeyForm(Form):
    """用于动态添加API密钥的表单"""
    key = StringField('API密钥', validators=[DataRequired()])


class LLMForm(FlaskForm):
    name = StringField('模型简称', validators=[DataRequired()])
    model = StringField('模型全称', validators=[DataRequired()])
    base_url = StringField('API基础URL', validators=[DataRequired()])
    api_keys = FieldList(
        StringField('API密钥', validators=[DataRequired()]),
        min_entries=1
    )
    # --- 新增字段 ---
    desc = TextAreaField('模型描述', validators=[Optional()])
    # Use FileField for the icon upload
    icon = FileField('模型图标 (可选)', validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'gif', 'svg'], '仅允许图片文件!')
    ])
    comment = TextAreaField('模型评价', validators=[Optional()])
    # --- 结束 ---
    submit = SubmitField('保存模型')