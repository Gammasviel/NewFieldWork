import logging
from flask import Blueprint, render_template, flash, redirect, url_for, request
from app.models import EvaluationHistory
from datetime import datetime
from sqlalchemy import func
from app.extensions import db

logger = logging.getLogger('history_routes')
history_bp = Blueprint('history', __name__, url_prefix='/history')

@history_bp.route('/')
def evaluation_history():
    """显示历史评估记录"""
    logger.info("Accessing evaluation history page.")
    try:
        available_dates_query = db.session.query(func.distinct(func.strftime('%Y-%m-%d', EvaluationHistory.timestamp))).all()
        available_dates = [d[0] for d in available_dates_query]

        selected_date_str = request.args.get('date')
        query = EvaluationHistory.query

        if selected_date_str:
            try:
                selected_dt = datetime.strptime(selected_date_str, '%Y-%m-%d')
                start_of_day = selected_dt.replace(hour=0, minute=0, second=0)
                end_of_day = selected_dt.replace(hour=23, minute=59, second=59)
                query = query.filter(EvaluationHistory.timestamp.between(start_of_day, end_of_day))
            except ValueError:
                flash('日期格式无效，请使用 YYYY-MM-DD 格式', 'warning')

        history_records = query.order_by(EvaluationHistory.timestamp.desc()).all()


        
        return render_template('public/evaluation_history.html', 
                             history_records=history_records,
                             available_dates=available_dates,
                             selected_date=selected_date_str)
    except Exception as e:
        logger.error(f"Error loading evaluation history: {e}", exc_info=True)
        flash('加载历史记录时发生错误，请检查日志。', 'danger')
        return render_template('public/evaluation_history.html', 
                             history_records=[],
                             available_dates=[],
                             selected_date=None)

@history_bp.route('/<int:history_id>')
def history_detail(history_id):
    """显示特定历史记录的详细数据"""
    logger.info(f"Accessing history detail for record {history_id}.")
    try:
        history_record = EvaluationHistory.query.get_or_404(history_id)
        sort_by = request.args.get('sort_by', 'avg_score')
        sort_order = request.args.get('sort_order', 'desc')
        leaderboard_data = history_record.evaluation_data
        reverse = sort_order == 'desc'
        if sort_by.startswith('dim_'):
            dim_id = sort_by.split('_')[1]
            leaderboard_data.sort(key=lambda x: x['dim_scores_display'].get(dim_id, -1), reverse=reverse)
        else:
            leaderboard_data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

        charts_data = {}
        dim_labels = [dim['name'] for dim in history_record.dimensions]
        for model_data in leaderboard_data:
            model_name = model_data['name']
            dim_scores = model_data.get('dim_scores', {})

            response_rates = []
            avg_scores = []

            for dim in history_record.dimensions:
                dim_id_int = dim['id']
                dim_id_str = str(dim['id'])
                score_info = dim_scores.get(dim_id_str) or dim_scores.get(dim_id_int) or {}
                response_rates.append(score_info.get('response_rate', 0))
                avg_scores.append(score_info.get('avg', 0))

            charts_data[model_name] = {
                'response_rate_by_dimension': {
                    'labels': dim_labels,
                    'datasets': [{'label': '响应率 (%)', 'data': response_rates, 'backgroundColor': 'rgba(75, 192, 192, 0.6)'}]
                },
                'avg_scores_by_dimension': {
                    'labels': dim_labels,
                    'datasets': [{'label': '平均得分', 'data': avg_scores, 'backgroundColor': 'rgba(153, 102, 255, 0.6)'}]
                }
            }

        overall_bias_analysis_data = []
        from app.models import Dimension

        bias_dim = Dimension.query.filter_by(name='偏见歧视', level=2).first()
        if bias_dim:
            l3_bias_dims = bias_dim.children

            for l3_dim in l3_bias_dims:
                dim_id_str = str(l3_dim.id)
                dim_id_int = l3_dim.id
                
                scores = []
                for model_data in leaderboard_data:
                    dim_scores = model_data.get('dim_scores', {})
                    score_info = dim_scores.get(dim_id_str) or dim_scores.get(dim_id_int)
                    if score_info and score_info.get('avg') is not None:
                        scores.append(score_info['avg'])

                if scores:
                    avg_score = sum(scores) / len(scores)
                    overall_bias_analysis_data.append({
                        'name': l3_dim.name,
                        'avg_score': avg_score
                    })
        else:
            logger.warning("Level 2 Dimension '偏见歧视' not found. Overall bias analysis will be skipped for history detail.")

        if leaderboard_data:
            avg_scores = [item['avg_score'] for item in leaderboard_data]
            response_rates = [item['response_rate'] for item in leaderboard_data]
            score_threshold = sum(avg_scores) / len(avg_scores)
            rate_threshold = sum(response_rates) / len(response_rates)
        else:
            score_threshold = 0
            rate_threshold = 0

        return render_template('public/history_detail.html',
                             history_record=history_record,
                             leaderboard=leaderboard_data,
                             l1_dimensions=history_record.dimensions,
                             score_threshold=score_threshold,
                             rate_threshold=rate_threshold,
                             current_sort_by=sort_by,
                             current_sort_order=sort_order,
                             charts_data=charts_data,
                             overall_bias_analysis_data=overall_bias_analysis_data)
    except Exception as e:
        logger.error(f"Error loading history detail {history_id}: {e}", exc_info=True)
        flash('加载历史记录详情时发生错误。', 'danger')
        return redirect(url_for('history.evaluation_history'))
