import logging
from flask import Blueprint, render_template, flash, redirect, url_for, request
from app.models import Question, EvaluationHistory
from app.extensions import db

from app.core.utils import generate_leaderboard_data
from app.core.tasks import generate_and_save_reports

public_leaderboard_bp = Blueprint('public_leaderboard', __name__)
logger = logging.getLogger('public_leaderboard_routes')

@public_leaderboard_bp.route('/')
def display_public_leaderboard():
    logger.info("Accessing public leaderboard page.")

    sort_by = request.args.get('sort_by', 'avg_score')
    sort_order = request.args.get('sort_order', 'desc')

    try:
        from app.models import Dimension, Rating, Answer, LLM
        from app.core.constants import RATERS

        data = generate_leaderboard_data(sort_by=sort_by, sort_order=sort_order)

        charts_data = {}
        for model_data in data['leaderboard']:
            model_name = model_data['name']

            response_rate_by_dim = {
                'labels': [dim['name'] for dim in data['l1_dimensions']],
                'datasets': [{
                    'label': '响应率',
                    'data': [model_data['dim_scores'][dim['id']]['response_rate'] for dim in data['l1_dimensions']]
                }]
            }

            avg_scores_by_dim = {
                'labels': [dim['name'] for dim in data['l1_dimensions']],
                'datasets': [{
                    'label': '平均分',
                    'data': [model_data['dim_scores'][dim['id']]['avg'] for dim in data['l1_dimensions']]
                }]
            }

            charts_data[model_name] = {
                'response_rate_by_dimension': response_rate_by_dim,
                'avg_scores_by_dimension': avg_scores_by_dim
            }

        # 计算所有模型的平均偏见歧视分析数据
        overall_bias_analysis_data = []
        bias_dim = Dimension.query.filter_by(name='偏见歧视', level=2).first()

        if bias_dim:
            l3_bias_dims = bias_dim.children
            rater_names = [rater for raters in RATERS.values() for rater in raters]
            model_ids = [m.id for m in LLM.query.filter(LLM.name.notin_(rater_names)).all()]

            logger.info(f"Found bias dimension with {len(l3_bias_dims)} sub-dimensions")
            logger.info(f"Calculating bias analysis for {len(model_ids)} models")

            for l3_dim in l3_bias_dims:
                from app.models import Question
                avg_score_result = db.session.query(
                    db.func.avg(Rating.score)
                ).join(Answer, Rating.answer_id == Answer.id)\
                 .join(Question, Answer.question_id == Question.id)\
                 .filter(
                    Answer.llm_id.in_(model_ids),
                    Question.dimension_id == l3_dim.id
                 ).scalar()

                if avg_score_result is not None:
                    overall_bias_analysis_data.append({
                        'name': l3_dim.name,
                        'avg_score': avg_score_result
                    })
                    logger.info(f"Bias dimension '{l3_dim.name}': avg_score={avg_score_result}")
                else:
                    logger.warning(f"No data for bias dimension '{l3_dim.name}'")

            logger.info(f"Overall bias analysis data: {len(overall_bias_analysis_data)} items")
        else:
            logger.warning("Level 2 Dimension '偏见歧视' not found in the database. Overall bias analysis will be skipped.")

        leaderboard_data = data['leaderboard']

        if leaderboard_data:
            avg_scores = [item['avg_score'] for item in leaderboard_data]
            response_rates = [item['response_rate'] for item in leaderboard_data]
            score_threshold = sum(avg_scores) / len(avg_scores)
            rate_threshold = sum(response_rates) / len(response_rates)
        else:
            score_threshold = 0
            rate_threshold = 0

        return render_template('public/public_leaderboard.html',
                               leaderboard=leaderboard_data,
                               l1_dimensions=data['l1_dimensions'],
                               score_threshold=score_threshold,
                               rate_threshold=rate_threshold,
                               current_sort_by=sort_by,
                               current_sort_order=sort_order,
                               charts_data=charts_data,
                               overall_bias_analysis_data=overall_bias_analysis_data)

    except Exception as e:
        logger.error(f"Error generating public leaderboard: {e}", exc_info=True)
        flash('生成榜单时发生错误，请检查日志。', 'danger')
        return render_template('public/public_leaderboard.html', 
                               leaderboard=leaderboard_data, 
                               l1_dimensions=data['l1_dimensions'],
                               score_threshold=score_threshold,
                               rate_threshold=rate_threshold,
                               current_sort_by=sort_by,
                               current_sort_order=sort_order,
                               charts_data=charts_data)

@public_leaderboard_bp.route('/update-all', methods=['POST'])
def update_all_models():
    from app.core.tasks import process_question
    logger.info("Received request to update all models for all questions.")
    try:
        all_question_ids = [q.id for q in Question.query.with_entities(Question.id).all()]
        if not all_question_ids:
            flash('系统中没有任何问题，无需更新。', 'warning')
            return redirect(url_for('public_leaderboard.display_public_leaderboard'))
        
        for qid in all_question_ids:
            process_question.delay(qid)
        
        try:
            current_data = generate_leaderboard_data()
            
            total_questions = Question.query.count()
            
            history_record = EvaluationHistory(
                dimensions=current_data['l1_dimensions'],
                evaluation_data=current_data['leaderboard'],
                extra_info={
                    'score_threshold': QUADRANT_SCORE_THRESHOLD,
                    'rate_threshold': QUADRANT_RESPONSE_RATE_THRESHOLD,
                    'total_models': len(current_data['leaderboard']),
                    'total_dimensions': len(current_data['l1_dimensions']),
                    'total_questions': total_questions,
                    'manual_save': False
                }
            )
            db.session.add(history_record)
            db.session.commit()
            generate_and_save_reports.delay(history_record.id)
            logger.info(f"Saved evaluation history snapshot with {len(current_data['leaderboard'])} models")
        except Exception as e:
            logger.error(f"Failed to save evaluation history: {e}", exc_info=True)
        
        flash(f'成功将 {len(all_question_ids)} 个问题的更新任务加入后台队列，并已保存当前评估快照。请稍后刷新查看结果。', 'success')
        logger.info(f"Queued update tasks for {len(all_question_ids)} questions.")
    except Exception as e:
        logger.error(f"Failed to queue update tasks: {e}", exc_info=True)
        flash('将更新任务加入队列时发生错误，请检查Celery服务是否正常。', 'danger')
    return redirect(url_for('public_leaderboard.display_public_leaderboard'))
