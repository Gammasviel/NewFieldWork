from flask import Blueprint, request, render_template
from sqlalchemy.orm import aliased
from models import db, Dimension, Rating, Setting, Answer, Question, LLM
from utils import calculate_weighted_average # <-- 1. Import the new function
import logging

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/dev/leaderboard')
logger = logging.getLogger('leaderboard_routes')

@leaderboard_bp.route('/')
def leaderboard():
    # Get filter parameters
    level1_id = request.args.get('level1', type=int)
    level2_id = request.args.get('level2', type=int)
    level3_id = request.args.get('level3', type=int)
    
    dim_level1 = aliased(Dimension)
    dim_level2 = aliased(Dimension)
    dim_level3 = aliased(Dimension)
    
    logger.info(f"Leaderboard accessed with filters: Level1_ID={level1_id}, Level2_ID={level2_id}, Level3_ID={level3_id}")
    
    # --- 2. Refactor the query to get weighted components ---
    # Use CASE to conditionally sum scores and counts based on question type
    query = db.session.query(
        LLM.name.label('model_name'),
        db.func.sum(db.case((Question.question_type == 'subjective', Rating.score), else_=0)).label('subj_score_total'),
        db.func.sum(db.case((Question.question_type == 'subjective', 1), else_=0)).label('subj_count'),
        db.func.sum(db.case((Question.question_type == 'objective', Rating.score), else_=0)).label('obj_score_total'),
        db.func.sum(db.case((Question.question_type == 'objective', 1), else_=0)).label('obj_count'),
        db.func.avg(Setting.total_score).label('avg_total'),
        (db.func.sum(db.case((Rating.is_responsive == True, 1), else_=0)) * 100.0 / db.func.count(Rating.id)).label('response_rate')
    ).select_from(Rating)
    
    query = query.join(Answer, Rating.answer_id == Answer.id)
    query = query.join(LLM, Answer.llm_id == LLM.id)
    query = query.join(Question, Answer.question_id == Question.id) # This join is crucial
    query = query.join(Setting, Question.question_type == Setting.question_type)
    query = query.join(dim_level3, Question.dimension_id == dim_level3.id)
    
    # Apply filters
    if level3_id:
        query = query.filter(dim_level3.id == level3_id)
    elif level2_id:
        query = query.join(dim_level2, dim_level3.parent == dim_level2.id)
        query = query.filter(dim_level2.id == level2_id)
    elif level1_id:
        query = query.join(dim_level2, dim_level3.parent == dim_level2.id)
        query = query.join(dim_level1, dim_level2.parent == dim_level1.id)
        query = query.filter(dim_level1.id == level1_id)
    
    # Group and fetch raw results
    raw_results = query.group_by(LLM.name).all()

    # --- 3. Process results in Python using the utility function ---
    leaderboard_data = []
    for item in raw_results:
        avg_score = calculate_weighted_average(
            item.subj_score_total,
            item.subj_count,
            item.obj_score_total,
            item.obj_count
        )
        leaderboard_data.append({
            'model_name': item.model_name,
            'avg_score': avg_score,
            'avg_total': item.avg_total,
            'response_rate': item.response_rate
        })
    
    # Sort by the newly calculated average score
    leaderboard_data.sort(key=lambda x: x['avg_score'], reverse=True)
    
    # Get dimension data for filters
    level1_dimensions = Dimension.query.filter_by(level=1).all()
    level2_dimensions = Dimension.query.filter(Dimension.level == 2, Dimension.parent.isnot(None)).all()
    level3_dimensions = Dimension.query.filter(Dimension.level == 3, Dimension.parent.isnot(None)).all()
    
    return render_template('leaderboard.html', 
                        leaderboard=leaderboard_data,
                        level1_dimensions=level1_dimensions,
                        level2_dimensions=level2_dimensions,
                        level3_dimensions=level3_dimensions,
                        level1_id=level1_id,
                        level2_id=level2_id,
                        level3_id=level3_id)