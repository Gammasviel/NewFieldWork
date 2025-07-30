from flask import render_template, Blueprint, flash, redirect, jsonify, url_for, request
from forms import QuestionForm
from models import db, Dimension, Question, Answer, Rating
from utils import process_question, process_all_questions
import threading

questions_bp = Blueprint('questions', __name__, url_prefix='/question')

@questions_bp.route('/add', methods=['GET', 'POST'])
def add_question():
    form = QuestionForm()
        
    # 获取所有维度数据
    level1_dims = Dimension.query.filter_by(level=1).all()
    level2_dims = Dimension.query.filter_by(level=2).all()
    level3_dims = Dimension.query.filter_by(level=3).all()
    
    # 组织维度数据用于前端展示
    dimension_options = {}
    for dim in level3_dims:
        level2 = dim.parent_ref
        level1 = level2.parent_ref if level2 else None
        
        if level1 and level2:
            level1_name = level1.name
            level2_name = level2.name
            level3_name = dim.name
            
            if level1_name not in dimension_options:
                dimension_options[level1_name] = {}
            if level2_name not in dimension_options[level1_name]:
                dimension_options[level1_name][level2_name] = []
            
            dimension_options[level1_name][level2_name].append((dim.id, level3_name))
    
    # 动态加载维度选择
    form.level1.choices = [(d.id, d.name) for d in level1_dims]
    form.level2.choices = [(d.id, d.name) for d in level2_dims]
    form.level3.choices = [(d.id, d.name) for d in level3_dims]
    
    if form.validate_on_submit():
        # 创建新问题
        new_question = Question(
            dimension_id=form.level3.data,
            question_type=form.question_type.data,
            content=form.content.data,
            answer=form.answer.data if form.question_type.data == 'objective' else None
        )
        db.session.add(new_question)
        db.session.commit()
        flash('题目添加成功', 'success')
        return redirect(url_for('index.index'))
    
    return render_template('add_question.html', form=form, dimension_options=dimension_options)


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