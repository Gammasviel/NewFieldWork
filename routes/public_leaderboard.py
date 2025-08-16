# .\routes\public_leaderboard.py

import logging
from flask import Blueprint, render_template, flash, redirect, url_for
from sqlalchemy.orm import aliased
from models import db, Dimension, Rating, Answer, Question, LLM
# from tasks import process_question  <-- 移除此处的全局导入
from config import RATERS

public_leaderboard_bp = Blueprint('public_leaderboard', __name__)
logger = logging.getLogger('public_leaderboard_routes')

@public_leaderboard_bp.route('/')
def display_public_leaderboard():
    """
    为普通用户展示的榜单页面。
    显示总体得分、响应率，以及在每个一级维度下的排名。
    """
    logger.info("Accessing public leaderboard page.")
    
    try:
        # 1. 获取所有需要评估的模型和所有一级维度
        rater_names = [rater for raters in RATERS.values() for rater in raters]
        models = LLM.query.filter(LLM.name.notin_(rater_names)).all()
        l1_dims = Dimension.query.filter_by(level=1).order_by(Dimension.id).all()

        # 2. 一次性查询所有相关的评分数据，并关联到一级维度
        dim_level3 = aliased(Dimension)
        dim_level2 = aliased(Dimension)
        dim_level1 = aliased(Dimension)

        ratings_query = db.session.query(
            Rating.score,
            Rating.is_responsive,
            Answer.llm_id,
            dim_level1.id.label('l1_dim_id')
        ).join(Answer, Rating.answer_id == Answer.id)\
         .join(Question, Answer.question_id == Question.id)\
         .join(dim_level3, Question.dimension_id == dim_level3.id)\
         .join(dim_level2, dim_level3.parent == dim_level2.id)\
         .join(dim_level1, dim_level2.parent == dim_level1.id)\
         .filter(Answer.llm_id.in_([m.id for m in models]))

        all_ratings_data = ratings_query.all()

        # 3. 在 Python 中处理和聚合数据
        model_scores = {}
        # 初始化数据结构
        for model in models:
            model_scores[model.id] = {
                'name': model.name,
                'total_score': 0,
                'rating_count': 0,
                'responsive_count': 0,
                'dim_scores': {dim.id: {'score': 0, 'count': 0} for dim in l1_dims}
            }

        # 聚合评分
        for r in all_ratings_data:
            if r.llm_id not in model_scores: continue
            # 聚合总分
            model_scores[r.llm_id]['total_score'] += r.score
            model_scores[r.llm_id]['rating_count'] += 1
            if r.is_responsive:
                model_scores[r.llm_id]['responsive_count'] += 1
            
            # 按维度聚合
            if r.l1_dim_id in model_scores[r.llm_id]['dim_scores']:
                model_scores[r.llm_id]['dim_scores'][r.l1_dim_id]['score'] += r.score
                model_scores[r.llm_id]['dim_scores'][r.l1_dim_id]['count'] += 1

        # 4. 计算平均分和排名
        leaderboard_data = []
        for model_id, data in model_scores.items():
            data['avg_score'] = (data['total_score'] / data['rating_count']) if data['rating_count'] > 0 else 0
            data['response_rate'] = (data['responsive_count'] / data['rating_count'] * 100) if data['rating_count'] > 0 else 0
            
            for dim_id, dim_data in data['dim_scores'].items():
                dim_data['avg'] = (dim_data['score'] / dim_data['count']) if dim_data['count'] > 0 else 0
            
            leaderboard_data.append(data)

        # 计算每个维度下的排名
        for dim in l1_dims:
            # 按当前维度的平均分降序排序
            leaderboard_data.sort(key=lambda x: x['dim_scores'][dim.id]['avg'], reverse=True)
            # 分配排名
            for i, model_data in enumerate(leaderboard_data):
                if 'ranks' not in model_data:
                    model_data['ranks'] = {}
                # 只有参与了该维度评估的才给予排名
                if model_data['dim_scores'][dim.id]['count'] > 0:
                    model_data['ranks'][dim.id] = i + 1
                else:
                    model_data['ranks'][dim.id] = '-' # 使用'-'表示未参与

        # 最终按总平均分进行排序
        leaderboard_data.sort(key=lambda x: x['avg_score'], reverse=True)
    except Exception as e:
        logger.error(f"Error generating public leaderboard: {e}", exc_info=True)
        flash('生成榜单时发生错误，请检查日志。', 'danger')
        leaderboard_data = []
        l1_dims = []

    return render_template('public_leaderboard.html', 
                           leaderboard=leaderboard_data, 
                           l1_dimensions=l1_dims)

@public_leaderboard_bp.route('/update-all', methods=['POST'])
def update_all_models():
    """
    触发一个Celery任务来更新所有问题的评估。
    """
    # --- 解决方案 ---
    # 在函数内部进行本地导入，打破循环依赖
    from tasks import process_question
    # --- 结束 ---
    
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