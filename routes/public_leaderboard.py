# .\routes\public_leaderboard.py

import logging
from flask import Blueprint, render_template, flash, redirect, url_for
from models import db, Question, LLM
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


@public_leaderboard_bp.route('/model/detail/<model_name>')
def model_detail(model_name):
    logger.info(f"Accessing detail page for model: {model_name}")
    
    llm = LLM.query.filter_by(name=model_name).first_or_404()
    
    # 1. Get full leaderboard data to find the rank and model details
    rater_names = [rater for raters in RATERS.values() for rater in raters]
    full_leaderboard_data = generate_leaderboard_data(rater_names)
    
    model_data = None
    model_rank = -1
    for i, data in enumerate(full_leaderboard_data['leaderboard']):
        if data['name'] == model_name:
            model_data = data
            model_rank = i + 1
            break
            
    if not model_data:
        flash('未找到该模型的评估数据。', 'warning')
        return redirect(url_for('public_leaderboard.display_public_leaderboard'))

    # 2. Prepare data for Chart 1: Radar Chart ((n+1) dimensions)
    radar_indicators = []
    radar_values = []
    
    # Add response rate first
    radar_indicators.append({'name': '响应率', 'max': 100})
    radar_values.append(model_data['response_rate'])
    
    # Add L1 dimension scores
    for dim in full_leaderboard_data['l1_dimensions']:
        radar_indicators.append({'name': dim['name'], 'max': 5}) # Assuming max score is 5
        score = model_data['dim_scores'][dim['id']]['avg']
        radar_values.append(score)

    radar_data = {
        'indicators': radar_indicators,
        'values': radar_values
    }

    # 3. Prepare data for Chart 2: Proportional Bar Chart
    # We will use a horizontal stacked bar chart to show proportions
    bar_data = []
    total_score_sum = 0
    for dim in full_leaderboard_data['l1_dimensions']:
        score = model_data['dim_scores'][dim['id']]['avg']
        # Only include dimensions where the model was actually evaluated
        if model_data['dim_scores'][dim['id']]['subj_count'] + model_data['dim_scores'][dim['id']]['obj_count'] > 0:
            bar_data.append({'name': dim['name'], 'value': score})
            total_score_sum += score
    
    # Calculate percentage for each dimension's score relative to the sum of scores
    if total_score_sum > 0:
        for item in bar_data:
            item['percentage'] = (item['value'] / total_score_sum) * 100

    return render_template(
        'model_detail.html', 
        llm=llm,
        model_rank=model_rank,
        radar_data=radar_data,
        bar_data=bar_data
    )