from models import db, Answer, Rating, Question, Setting, LLM
import time
from config import DEFAULT_CRITERIA, QUESTION_TEMPLATE, RATING_TEMPLATE, RATERS, RATING_FAIL_RETRIES, DEFAULT_TOTAL_SCORE
from llm import clients

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

def process_question(app, question_id):
    with app.app_context():
        question = db.session.get(Question, question_id)
        if not question:
            return

        Answer.query.filter_by(question_id=question_id).delete()
        
            
        setting = Setting.query.filter_by(question_type=question.question_type).first()
        
        criteria = setting.criteria if setting else DEFAULT_CRITERIA[question.question_type]
        total_score = setting.total_score if setting else DEFAULT_TOTAL_SCORE
        
        rater_llms_all = LLM.query.filter(LLM.name.in_([rater for raters in RATERS.values() for rater in raters])).all()
        rater_ids_all = [rater.id for rater in rater_llms_all]
        
        rater_llm = LLM.query.filter(LLM.name.in_(RATERS[question.question_type])).all()
        rater_ids = [rater.id for rater in rater_llm]

        # 2. 让所有待评估模型生成回答并存入数据库
        new_answers = generate_answers(question, rater_ids_all)

        # 3. 遍历每个新生成的回答，让评委模型进行评分
        for answer in new_answers:
            rate_answer(answer, question, criteria, total_score, rater_ids)
            
        # 4. 提交本次问题处理的所有数据库事务（包括开头的删除和后续的新增）
        db.session.commit()


def process_all_questions(app):
    with app.app_context():
        # 获取所有问题ID
        question_ids = [q.id for q in Question.query.all()]
        for qid in question_ids:
            process_question(qid)