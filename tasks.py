from app import create_app
from models import db, Question, Answer, Setting, LLM, Rating
from config import DEFAULT_CRITERIA, QUESTION_TEMPLATE, RATING_TEMPLATE, RATERS, RATING_FAIL_RETRIES, DEFAULT_TOTAL_SCORE
from llm import clients
from celery import Celery

# 1. 创建一个 Flask app 实例以获取其配置
flask_app = create_app()

# 2. 创建 Celery 实例
celery = Celery(
    flask_app.import_name,
    backend=flask_app.config['CELERY_RESULT_BACKEND'],
    broker=flask_app.config['CELERY_BROKER_URL']
)

# 3. 将 Flask 的配置更新到 Celery 的配置中
celery.conf.update(flask_app.config)


# 4. (关键步骤) 定义一个任务基类，确保任务在 Flask 的应用上下文中运行
#    这样任务内部就可以安全地使用 db.session, current_app 等
class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask


# 5. 将 process_question 定义为一个 Celery 任务
@celery.task
def process_question(question_id):
    """
    这是一个 Celery 任务，它在独立的 Worker 进程中运行。
    注意：函数签名不再需要 app 参数。
    """
    question = db.session.get(Question, question_id)
    if not question:
        # 可以添加日志记录
        print(f"任务失败：找不到 ID 为 {question_id} 的问题。")
        return

    # 删除旧的答案和评分
    Answer.query.filter_by(question_id=question_id).delete()
    
    # 获取设置和评委
    setting = Setting.query.filter_by(question_type=question.question_type).first()
    criteria = setting.criteria if setting else DEFAULT_CRITERIA[question.question_type]
    total_score = setting.total_score if setting else DEFAULT_TOTAL_SCORE
    
    rater_llms_all = LLM.query.filter(LLM.name.in_([rater for raters in RATERS.values() for rater in raters])).all()
    rater_ids_all = [rater.id for rater in rater_llms_all]
    
    rater_llm = LLM.query.filter(LLM.name.in_(RATERS[question.question_type])).all()
    rater_ids = [rater.id for rater in rater_llm]

    # 生成回答 (utils.py 中的函数可以直接复用或移入此类)
    # 注意：这些函数现在将使用在任务上下文中可用的 db.session
    # from utils import generate_answers, rate_answer
    new_answers = generate_answers(question, rater_ids_all)

    # 评分
    for answer in new_answers:
        rate_answer(answer, question, criteria, total_score, rater_ids)
        
    db.session.commit()
    print(f"成功处理完问题 {question_id}。")
    
def generate_answers(question: Question, rater_ids_all: list[int]) -> list[Answer]:
    question_prompt = QUESTION_TEMPLATE[question.question_type].format(question.content)
    responses = clients.generate_responses(question_prompt, exclusions=rater_ids_all)
    
    new_answers = []
    for llm_id, response_content in responses.items():
        answer = Answer(
            question_id=question.id,
            llm_id=llm_id,
            content=response_content
        )
        db.session.add(answer)
        new_answers.append(answer)
    
    db.session.flush()
    return new_answers

def rate_answer(answer: Answer, question: Question, criteria: str, total_score: str, rater_ids: list[int]):
    valid_scores = []
    rater_comments = []

    if question.question_type == 'objective':
        rating_prompt = RATING_TEMPLATE['objective'].format(
            question=question.content,
            answer=question.answer,
            criteria=criteria,
            response=answer.content
        )
    else:
        rating_prompt = RATING_TEMPLATE['subjective'].format(
            question=question.content,
            criteria=criteria,
            response=answer.content
        )

    # 遍历所有评委模型进行评分
    for rater_id in rater_ids:
        score = -1.0
        for _ in range(RATING_FAIL_RETRIES):
            raw_score = clients.generate_response(rating_prompt, rater_id)
            try:
                parsed_score = float(raw_score)
                if 0 <= parsed_score <= total_score:
                    score = parsed_score
                    break
            except (ValueError, TypeError):
                pass
        
        rater_llm = db.session.get(LLM, rater_id)
        rater_name = rater_llm.name if rater_llm else f"RaterID_{rater_id}"

        if score != -1.0:
            valid_scores.append(score)
        rater_comments.append(f'{rater_name}: {score if score != -1.0 else "Rating Failed"}')
    
    final_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    is_responsive = 2.5 <= final_score <= 3.5

    # 创建并存储最终的评分记录
    rating = Rating(
        answer_id=answer.id,
        llm_id=answer.llm_id,
        score=final_score,
        is_responsive=is_responsive, # 在这里设置 is_responsive 的值
        comment='\n'.join(rater_comments)
    )
    db.session.add(rating)
