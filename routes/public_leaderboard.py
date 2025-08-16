# .\routes\public_leaderboard.py

import logging
from flask import Blueprint, render_template, flash, redirect, url_for
from models import db, Question
from config import (
    RATERS, 
    QUADRANT_SCORE_THRESHOLD, 
    QUADRANT_RESPONSE_RATE_THRESHOLD
)
# <-- 1. 导入新的工具函数 -->
from utils import generate_leaderboard_data

public_leaderboard_bp = Blueprint('public_leaderboard', __name__)
logger = logging.getLogger('public_leaderboard_routes')

@public_leaderboard_bp.route('/')
def display_public_leaderboard():
    logger.info("Accessing public leaderboard page.")
    
    try:
        # <-- 2. 路由现在只负责调用工具函数和渲染 -->
        rater_names = [rater for raters in RATERS.values() for rater in raters]
        data = generate_leaderboard_data(rater_names)
        
        return render_template('public_leaderboard.html', 
                               leaderboard=data['leaderboard'], 
                               l1_dimensions=data['l1_dimensions'],
                               score_threshold=QUADRANT_SCORE_THRESHOLD,
                               rate_threshold=QUADRANT_RESPONSE_RATE_THRESHOLD)

    except Exception as e:
        logger.error(f"Error generating public leaderboard: {e}", exc_info=True)
        flash('生成榜单时发生错误，请检查日志。', 'danger')
        return render_template('public_leaderboard.html', 
                               leaderboard=[], 
                               l1_dimensions=[],
                               score_threshold=QUADRANT_SCORE_THRESHOLD,
                               rate_threshold=QUADRANT_RESPONSE_RATE_THRESHOLD)


@public_leaderboard_bp.route('/model-detail/<model_name>')
def model_detail(model_name):
    logger.info(f"Accessing detail page for model: {model_name}")
    return render_template('model_detail.html', model_name=model_name)


@public_leaderboard_bp.route('/update-all', methods=['POST'])
def update_all_models():
    from tasks import process_question
    logger.info("Received request to update all models for all questions.")
    try:
        all_question_ids = [q.id for q in Question.query.with_entities(Question.id).all()]
        if not all_question_ids:
            flash('系统中没有任何问题，无需更新。', 'warning')
            return redirect(url_for('public_leaderboard.display_public_leaderboard'))
        for qid in all_question_ids:
            process_question.delay(qid)
        flash(f'成功将 {len(all_question_ids)} 个问题的更新任务加入后台队列。请稍后刷新查看结果。', 'success')
        logger.info(f"Queued update tasks for {len(all_question_ids)} questions.")
    except Exception as e:
        logger.error(f"Failed to queue update tasks: {e}", exc_info=True)
        flash('将更新任务加入队列时发生错误，请检查Celery服务是否正常。', 'danger')
    return redirect(url_for('public_leaderboard.display_public_leaderboard'))