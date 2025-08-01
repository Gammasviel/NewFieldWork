from flask import render_template, Blueprint, flash, redirect, url_for, request, jsonify
from forms import QuestionForm
from models import db, Dimension, Question, Answer, Rating
from utils import process_question, process_all_questions
import threading

questions_bp = Blueprint('questions', __name__, url_prefix='/question')

@questions_bp.route('/add', methods=['GET', 'POST'])
def add_question():
    form = QuestionForm()
    
    # 1. 始终填充一级维度的选项
    level1_dims = Dimension.query.filter_by(level=1).order_by(Dimension.name).all()
    form.level1.choices = [(d.id, d.name) for d in level1_dims]
    
    # 2. 如果是POST请求（即表单已提交），则根据提交的数据填充二级和三级选项
    #    这是为了在验证失败时，能够正确回显用户的选择
    if request.method == 'POST':
        level1_id = form.level1.data
        if level1_id:
            level2_dims = Dimension.query.filter_by(level=2, parent=level1_id).order_by(Dimension.name).all()
            form.level2.choices = [(d.id, d.name) for d in level2_dims]
        else:
            form.level2.choices = []

        level2_id = form.level2.data
        if level2_id:
            level3_dims = Dimension.query.filter_by(level=3, parent=level2_id).order_by(Dimension.name).all()
            form.level3.choices = [(d.id, d.name) for d in level3_dims]
        else:
            form.level3.choices = []
    else:
        # 3. 如果是GET请求（首次加载页面），则二级和三级选项为空，等待用户选择
        form.level2.choices = []
        form.level3.choices = []

    # 4. 为所有下拉菜单添加默认的提示选项
    form.level1.choices.insert(0, ('', '请选择一级维度'))
    form.level2.choices.insert(0, ('', '请选择二级维度'))
    form.level3.choices.insert(0, ('', '请选择三级维度'))
    
    if form.validate_on_submit():
        # 创建新问题
        new_question = Question(
            dimension_id=int(form.level3.data),
            question_type=form.question_type.data,
            content=form.content.data,
            answer=form.answer.data if form.question_type.data == 'objective' else None
        )
        db.session.add(new_question)
        db.session.commit()
        flash('题目添加成功', 'success')
        return redirect(url_for('index.index'))
    
    # 注意：我们不再需要向模板传递 dimension_options 字典
    return render_template('add_question.html', form=form)


@questions_bp.route('/update', methods=['GET', 'POST'])
def update_questions():
    if request.method == 'POST':
        question_id = request.form.get('question_id')
        if question_id:
            # 在后台线程中处理单个问题
            thread = threading.Thread(target=process_question, args=(question_id,))
            thread.start()
            return jsonify({'status': 'processing', 'question_id': question_id})
        else:
            # 处理所有问题
            thread = threading.Thread(target=process_all_questions)
            thread.start()
            return jsonify({'status': 'processing_all'})
    
    # 获取所有问题
    questions = Question.query.all()
    return render_template('update_questions.html', questions=questions)

@questions_bp.route('/<int:question_id>')
def question_detail(question_id):
    question = Question.query.get_or_404(question_id)
    answers = Answer.query.filter_by(question_id=question_id).options(
        db.joinedload(Answer.llm),
        db.joinedload(Answer.ratings).joinedload(Rating.llm)
    ).all()
    
    return render_template('question_detail.html', question=question, answers=answers)