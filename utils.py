from models import db, Answer, Rating, Question, Setting, LLM
import random
import time
from config import AI_MODELS, DEFAULT_CRITERIA, QUESTION_TEMPLATE, RATING_TEMPLATE, RATERS, RATING_FAIL_RETRIES, DEFAULT_TOTAL_SCORE
from llm import clients

def process_question(question_id):
    """处理单个问题：让所有AI模型回答并由其他模型评分"""
    from app import app
    with app.app_context():
        question = db.session.get(Question, question_id)
        if not question:
            return
        
        # 获取当前评分标准
        setting = Setting.query.filter_by(question_type = question.question_type).first()
        criteria = setting.criteria if setting else DEFAULT_CRITERIA[question.question_type]
        total_score = setting.total_score if setting else DEFAULT_TOTAL_SCORE
        
        raters = [LLM.query.filter_by(name = rater).first().id for rater in RATERS]
        responses = clients.generate_responses(QUESTION_TEMPLATE.format(question.content), exclusions=raters)
        for id in responses:
            answer = Answer(
                question_id = question_id,
                llm_id = id,
                content = responses[id]
            )
            db.session.add(answer)
            db.session.flush()
            
            scores = []
            comments = []
            for rater in raters:

                for _ in range(RATING_FAIL_RETRIES):
                    
                    if question.question_type == 'objective':
                        prompt = RATING_TEMPLATE[question.question_type].format(
                            question = question.question_type,
                            answer = question.answer,
                            criteria = criteria,
                            response = responses[id]
                        )
                    else:
                        prompt = RATING_TEMPLATE[question.question_type].format(
                            question = question.question_type,
                            criteria = criteria,
                            response = responses[id]
                        )
                    raw_score = clients.generate_response(prompt, rater)
                    try:
                        score = float(raw_score)
                        if 0 < score < total_score:
                            scores.append(score)
                            break
                    except:
                        pass
                else:
                    score = -1
                
                comments.append(f'{rater}: {score}')
                
            rating = Rating(
                answer_id = answer.id,
                llm_id = id,
                score = sum(scores) / len(scores),
                comment = '\n'.join(comments)
            )
            db.session.add(rating)
        db.session.commit()
                    
def process_all_questions():
    """处理所有问题：重新回答和评分"""
    from app import app
    with app.app_context():
        # 获取所有问题ID
        question_ids = [q.id for q in Question.query.all()]
        for qid in question_ids:
            process_question(qid)