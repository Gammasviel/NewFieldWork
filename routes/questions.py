# .\routes\questions.py

from flask import render_template, Blueprint, flash, redirect, url_for, request, jsonify, current_app
from forms import QuestionForm
from models import db, Dimension, Question, Answer, Rating
from tasks import process_question

questions_bp = Blueprint('questions', __name__, url_prefix='/question')

@questions_bp.route('/add', methods=['GET', 'POST'])
def add_question():
    form = QuestionForm()
    
    level1_dims = Dimension.query.filter_by(level=1).order_by(Dimension.name).all()
    form.level1.choices = [(d.id, d.name) for d in level1_dims]
    
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
        form.level2.choices = []
        form.level3.choices = []

    form.level1.choices.insert(0, ('', '请选择一级维度'))
    form.level2.choices.insert(0, ('', '请选择二级维度'))
    form.level3.choices.insert(0, ('', '请选择三级维度'))
    
    if form.validate_on_submit():
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
    
    return render_template('add_question.html', form=form)

@questions_bp.route('/<int:question_id>')
def question_detail(question_id):
    question = Question.query.get_or_404(question_id)
    answers = Answer.query.filter_by(question_id=question_id).options(
        db.joinedload(Answer.llm),
        db.joinedload(Answer.ratings).joinedload(Rating.llm)
    ).all()
    
    return render_template('question_detail.html', question=question, answers=answers)


@questions_bp.route('/delete/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    """处理单个问题的删除"""
    question = Question.query.get_or_404(question_id)
    db.session.delete(question)
    db.session.commit()
    flash(f'题目 ID:{question.id} 已被成功删除。', 'success')
    
    return redirect(url_for('questions.update_questions'))

@questions_bp.route('/update', methods=['GET', 'POST'])
def update_questions():
    if request.method == 'POST':
        question_id = request.form.get('question_id')
        if question_id:
            # 不再创建线程，而是调用 .delay() 方法将任务发送到队列
            process_question.delay(int(question_id))
            flash(f'问题 {question_id} 的更新任务已加入队列。', 'info')
            return jsonify({'status': 'queued', 'question_id': question_id})
    
    questions = Question.query.order_by(Question.id.desc()).all()
    return render_template('update_questions.html', questions=questions)


@questions_bp.route('/bulk_action', methods=['POST'])
def bulk_action():
    action = request.form.get('action')
    question_ids = request.form.getlist('question_ids')
    
    if not question_ids:
        flash('没有选择任何题目。', 'warning')
        return redirect(url_for('questions.update_questions'))
    
    if action == 'update':
        for qid in question_ids:
            # 调用 .delay()
            process_question.delay(int(qid))
        flash(f'已将 {len(question_ids)} 个问题的更新任务加入后台队列。', 'info')
        
    elif action == 'delete':
        Question.query.filter(Question.id.in_(question_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'已成功删除 {len(question_ids)} 个选定的问题。', 'success')
        
    else:
        flash('无效操作。', 'danger')

    return redirect(url_for('questions.update_questions'))