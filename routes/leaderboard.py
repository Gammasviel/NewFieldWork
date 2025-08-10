from flask import Blueprint, request, render_template
from sqlalchemy.orm import aliased
from models import db, Dimension, Rating, Setting, Answer, Question, LLM
from module_logger import get_module_logger

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')
logger = get_module_logger('leaderboard_routes')

@leaderboard_bp.route('/')
def leaderboard():
    # 获取筛选参数
    level1_id = request.args.get('level1', type=int)
    level2_id = request.args.get('level2', type=int)
    level3_id = request.args.get('level3', type=int)
    
    # 构建查询
    dim_level1 = aliased(Dimension)
    dim_level2 = aliased(Dimension)
    dim_level3 = aliased(Dimension)
    
    logger.info(f"Leaderboard accessed with filters: Level1_ID={level1_id}, Level2_ID={level2_id}, Level3_ID={level3_id}")
    
    # 【修改点】重构查询以包含响应率计算
    query = db.session.query(
        LLM.name.label('model_name'),
        db.func.avg(Rating.score).label('avg_score'),
        db.func.avg(Setting.total_score).label('avg_total'),
        # 计算响应率：(响应为True的评分数 * 100.0 / 总评分数)
        (db.func.sum(db.case((Rating.is_responsive == True, 1), else_=0)) * 100.0 / db.func.count(Rating.id)).label('response_rate')
    ).select_from(Rating) # 从 Rating 开始查询更直观
    
    # 添加连接
    query = query.join(Answer, Rating.answer_id == Answer.id)
    query = query.join(LLM, Answer.llm_id == LLM.id)
    query = query.join(Question, Answer.question_id == Question.id)
    query = query.join(Setting, Question.question_type == Setting.question_type)
    query = query.join(dim_level3, Question.dimension_id == dim_level3.id)
    
    # 应用筛选条件
    if level3_id:
        query = query.filter(dim_level3.id == level3_id)
    elif level2_id:
        query = query.join(dim_level2, dim_level3.parent == dim_level2.id)
        query = query.filter(dim_level2.id == level2_id)
    elif level1_id:
        query = query.join(dim_level2, dim_level3.parent == dim_level2.id)
        query = query.join(dim_level1, dim_level2.parent == dim_level1.id)
        query = query.filter(dim_level1.id == level1_id)
    
    # 分组并排序
    leaderboard = query.group_by(LLM.name).order_by(db.desc('avg_score')).all()
    
    # 【删除点】不再需要计算问题数量
    # question_count 的整个计算逻辑块已被移除

    # 获取维度数据用于筛选
    level1_dimensions = Dimension.query.filter_by(level=1).all()
    # 为了筛选器联动，我们只获取有父级的一二级维度
    level2_dimensions = Dimension.query.filter(Dimension.level == 2, Dimension.parent.isnot(None)).all()
    level3_dimensions = Dimension.query.filter(Dimension.level == 3, Dimension.parent.isnot(None)).all()
    
    return render_template('leaderboard.html', 
                        leaderboard=leaderboard,
                        level1_dimensions=level1_dimensions,
                        level2_dimensions=level2_dimensions,
                        level3_dimensions=level3_dimensions,
                        # 【删除点】移除 levelX_id 的传递，因为筛选器现在是自提交的
                        level1_id=level1_id,
                        level2_id=level2_id,
                        level3_id=level3_id)