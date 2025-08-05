from models import db, Answer, Rating, Question, Setting, LLM
import random
import time
from config import AI_MODELS, DEFAULT_CRITERIA, QUESTION_TEMPLATE, RATING_TEMPLATE, RATERS, RATING_FAIL_RETRIES, DEFAULT_TOTAL_SCORE
from llm import clients

def get_evaluation_context(question: Question) -> dict:
    setting = Setting.query.filter_by(question_type=question.question_type).first()
    
    criteria = setting.criteria if setting else DEFAULT_CRITERIA[question.question_type]
    total_score = setting.total_score if setting else DEFAULT_TOTAL_SCORE
    
    rater_llms = LLM.query.filter(LLM.name.in_(RATERS)).all()
    rater_ids = [rater.id for rater in rater_llms]
    
    return {
        'criteria': criteria,
        'total_score': total_score,
        'rater_ids': rater_ids
    }

def generate_answer(question: Question, rater_ids: list[int]) -> list[Answer]:
    question_prompt = QUESTION_TEMPLATE[question.question_type].format(question.content)
    
    # 获取除评委外的所有模型的回答
    responses = clients.generate_responses(question_prompt, exclusions=rater_ids)
    
    new_answers = []
    for llm_id, response_content in responses.items():
        answer = Answer(
            question_id=question.id,
            llm_id=llm_id,
            content=response_content
        )
        db.session.add(answer)
        new_answers.append(answer)
    
    # 刷新会话，为新答案对象分配ID，以便后续关联评分
    db.session.flush()
    return new_answers

def rate_answer(answer: Answer, question: Question, context: dict):
    valid_scores = []
    rater_comments = []

    # 为此回答构建评分Prompt
    if question.question_type == 'objective':
        rating_prompt = RATING_TEMPLATE['objective'].format(
            question=question.content,
            answer=question.answer,
            criteria=context['criteria'],
            response=answer.content
        )
    else:  # 'subjective'
        rating_prompt = RATING_TEMPLATE['subjective'].format(
            question=question.content,
            criteria=context['criteria'],
            response=answer.content
        )

    # 遍历所有评委模型进行评分
    for rater_id in context['rater_ids']:
        score = -1.0
        # 包含评分失败的重试逻辑
        for _ in range(RATING_FAIL_RETRIES):
            raw_score = clients.generate_response(rating_prompt, rater_id)
            try:
                parsed_score = float(raw_score)
                # 确保分数在有效范围内
                if 0 <= parsed_score <= context['total_score']:
                    score = parsed_score
                    break
            except (ValueError, TypeError):
                # 如果解析失败，将进行下一次重试
                pass
        
        rater_llm = db.session.get(LLM, rater_id)
        rater_name = rater_llm.name if rater_llm else f"RaterID_{rater_id}"

        if score != -1.0:
            valid_scores.append(score)
        rater_comments.append(f'{rater_name}: {score if score != -1.0 else "Rating Failed"}')

    # 计算平均分，避免除以零的错误
    final_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    
    # 创建并存储最终的评分记录
    rating = Rating(
        answer_id=answer.id,
        llm_id=answer.llm_id,  # 评分是针对“回答者”模型的
        score=final_score,
        comment='\n'.join(rater_comments)
    )
    db.session.add(rating)

def process_question(question_id):
    from app import app
    with app.app_context():
        question = db.session.get(Question, question_id)
        if not question:
            print(f"Error: Question with ID {question_id} not found.")
            return

        # 1. 获取评估所需的全部上下文信息
        context = get_evaluation_context(question)
        if not context['rater_ids']:
            print("Warning: No rater models found in the database. Aborting evaluation.")
            return

        # 2. 让所有待评估模型生成回答并存入数据库
        new_answers = generate_answer(question, context['rater_ids'])

        # 3. 遍历每个新生成的回答，让评委模型进行评分
        for answer in new_answers:
            rate_answer(answer, question, context)
            
        # 4. 提交本次问题处理的所有数据库事务
        db.session.commit()
        print(f"Successfully processed question {question_id}.")

def process_all_questions():
    """处理所有问题：重新回答和评分"""
    from app import app
    with app.app_context():
        # 获取所有问题ID
        question_ids = [q.id for q in Question.query.all()]
        for qid in question_ids:
            process_question(qid)