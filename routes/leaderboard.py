from flask import Blueprint, request, render_template
from sqlalchemy.orm import aliased
from models import db, Dimension, Rating, Setting, Answer, Question, LLM

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

@leaderboard_bp.route('/')
def leaderboard():
    # 获取筛选参数
    level1_id = request.args.get('level1')
    level2_id = request.args.get('level2')
    level3_id = request.args.get('level3')
    
    # 构建查询
    
    # 明确构建查询路径
    dim_level1 = aliased(Dimension)
    dim_level2 = aliased(Dimension)
    dim_level3 = aliased(Dimension)
    

    query = db.session.query(
        LLM.name.label('model_name'),
        db.func.avg(Rating.score).label('avg_score'),
        db.func.avg(Setting.total_score).label('avg_total')
    ).select_from(Answer)  # 明确指定查询起点
    # 添加连接
    query = query.join(LLM, Answer.llm_id == LLM.id)
    query = query.join(Question, Question.id == Answer.question_id)
    query = query.join(dim_level3, dim_level3.id == Question.dimension_id)
    query = query.join(Rating, Rating.answer_id == Answer.id)
    
    # 应用筛选条件
    if level3_id:
        query = query.filter(dim_level3.id == level3_id)
    elif level2_id:
        query = query.join(dim_level2, dim_level2.id == dim_level3.parent)
        query = query.filter(dim_level2.id == level2_id)
    elif level1_id:
        query = query.join(dim_level2, dim_level2.id == dim_level3.parent)
        query = query.join(dim_level1, dim_level1.id == dim_level2.parent)
        query = query.filter(dim_level1.id == level1_id)
    
    # 分组并排序
    leaderboard = query.group_by(LLM.name).order_by(db.desc('avg_score')).all()
    
    # 计算问题数量
    if level3_id:
        question_count = Question.query.filter_by(dimension_id=level3_id).count()
    elif level2_id:
        subquery = db.session.query(Dimension.id).filter_by(parent=level2_id)
        question_count = Question.query.filter(Question.dimension_id.in_(subquery)).count()
    elif level1_id:
        level2_ids = db.session.query(Dimension.id).filter_by(parent=level1_id)
        level3_ids = db.session.query(Dimension.id).filter(Dimension.parent.in_(level2_ids))
        question_count = Question.query.filter(Question.dimension_id.in_(level3_ids)).count()
    else:
        question_count = Question.query.count()
    
    # 获取维度数据用于筛选
    level1_dimensions = Dimension.query.filter_by(level=1).all()
    level2_dimensions = Dimension.query.filter_by(level=2).all()
    level3_dimensions = Dimension.query.filter_by(level=3).all()
    
    return render_template('leaderboard.html', 
                        leaderboard=leaderboard,
                        level1_dimensions=level1_dimensions,
                        level2_dimensions=level2_dimensions,
                        level3_dimensions=level3_dimensions,
                        question_count=question_count,
                        level1_id=level1_id,
                        level2_id=level2_id,
                        level3_id=level3_id)