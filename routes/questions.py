from flask import render_template, Blueprint, flash, redirect, url_for, request, jsonify
from forms import QuestionForm
from models import Dimension, Question, Answer, Rating
from extensions import db
import logging

questions_bp = Blueprint('questions', __name__, url_prefix='/dev/question')
logger = logging.getLogger('question_routes')

@questions_bp.route('/add', methods=['GET', 'POST'])
def add_question():
    form = QuestionForm()
    
    # 动态加载维度的逻辑保持不变
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
        logger.info(f"Attempting to add new '{form.question_type.data}' question.")
        new_question = Question(
            dimension_id=int(form.level3.data),
            question_type=form.question_type.data,
            content=form.content.data,
            answer=form.answer.data if form.question_type.data == 'objective' else None
        )
        db.session.add(new_question)
        db.session.commit()
        flash('题目添加成功', 'success')
        logger.info(f"Successfully added question, new ID: {new_question.id}.")
        return redirect(url_for('questions.update_questions')) # 改为跳转到问题列表页更友好
    
    return render_template('add_question.html', form=form)

# --- 这是被遗漏的函数 ---
@questions_bp.route('/<int:question_id>')
def question_detail(question_id):
    logger.info(f"Accessed detail page for Question ID: {question_id}.") # <-- 添加日志
    question = Question.query.get_or_404(question_id)
    answers = Answer.query.filter_by(question_id=question_id).options(
        db.joinedload(Answer.llm),
        db.joinedload(Answer.ratings) # 简化了这里的 joinedload，因为 rater 信息在 comment 中
    ).all()
    
    return render_template('question_detail.html', question=question, answers=answers)


@questions_bp.route('/delete/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    """处理单个问题的删除"""
    question = Question.query.get_or_404(question_id)
    logger.warning(f"Attempting to delete question ID: {question.id}.")
    db.session.delete(question)
    db.session.commit()
    flash(f'题目 ID:{question.id} 已被成功删除。', 'success')
    logger.info(f"Successfully deleted question ID: {question.id}.")
    
    return redirect(url_for('questions.update_questions'))

@questions_bp.route('/update', methods=['GET', 'POST'])
def update_questions():
    if request.method == 'POST':
        question_id = request.form.get('question_id')
        if question_id:
            from tasks import process_question
            
            logger.info(f"Queuing single question update task for question ID: {question_id}.")
            process_question.delay(int(question_id))
            
            # 【解决方案 2.1】不再使用 flash，直接在 JSON 中返回消息
            return jsonify({
                'status': 'queued', 
                'question_id': question_id,
                'message': f'问题 {question_id} 的更新任务已成功加入队列。'
            })
    
    logger.info("Accessed question list and update page.")
    questions = Question.query.order_by(Question.id.desc()).all()
    return render_template('update_questions.html', questions=questions)

# 【解决方案 2.2】添加一个新的路由，用于前端轮询问题状态
@questions_bp.route('/status/<int:question_id>', methods=['GET'])
def get_question_status(question_id):
    question = Question.query.get_or_404(question_id)
    # 检查这个问题是否已经有答案了
    if question.answers:
        return jsonify({'status': '已评估'})
    else:
        return jsonify({'status': '处理中'})

@questions_bp.route('/bulk_action', methods=['POST'])
def bulk_action():
    action = request.form.get('action')
    question_ids = request.form.getlist('question_ids')
    
    if not question_ids:
        flash('没有选择任何题目。', 'warning')
        logger.warning("Bulk action initiated but no questions were selected.")
        return redirect(url_for('questions.update_questions'))
        
    logger.info(f"Performing bulk action '{action}' on {len(question_ids)} questions. IDs: {question_ids}")
    
    if action == 'update':
        from tasks import process_question
        
        for qid in question_ids:
            process_question.delay(int(qid))
        flash(f'已将 {len(question_ids)} 个问题的更新任务加入后台队列。', 'info')
        
    elif action == 'delete':
        logger.warning(f"Bulk deleting questions with IDs: {question_ids}.")
        Question.query.filter(Question.id.in_(question_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'已成功删除 {len(question_ids)} 个选定的问题。', 'success')
        logger.info(f"Successfully bulk deleted {len(question_ids)} questions.")
        
    else:
        flash('无效操作。', 'danger')
        logger.error(f"Invalid bulk action attempted: {action}.")

    return redirect(url_for('questions.update_questions'))