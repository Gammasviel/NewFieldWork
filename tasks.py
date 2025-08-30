# .\tasks.py

import logging
from app import create_app
from extensions import db
from models import Question, Answer, Setting, LLM, Rating
from config import DEFAULT_CRITERIA, QUESTION_TEMPLATE, RATERS, DEFAULT_TOTAL_SCORE
from llm import clients
from celery import Celery, group
from celery.schedules import crontab
from celery.signals import after_setup_logger
from utils import setup_logging, rate_answer # <-- 1. 修改导入

logger = logging.getLogger('celery_tasks')

flask_app = create_app()
celery = Celery(
    flask_app.import_name,
    backend=flask_app.config['CELERY_RESULT_BACKEND'],
    broker=flask_app.config['CELERY_BROKER_URL']
)
celery.conf.update(flask_app.config)

celery.conf.beat_schedule = {
    'update-all-models-every-sunday': {
        'task': 'tasks.update_all_models_task',
        'schedule': crontab(hour=0, minute=0, day_of_week='sunday'),
    },
}

class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask

@after_setup_logger.connect
def setup_celery_logging(logger, **kwargs):
    setup_logging()
    logging.info("Celery worker logger configured.")

@celery.task
def process_question(question_id):
    logger.info(f"--- [Master Task] FORCING REGENERATION for Question ID: {question_id} ---")
    
    question = db.session.get(Question, question_id)
    if not question:
        logger.error(f"[Master Task] Failed: Could not find Question with ID {question_id}.")
        return

    answer_ids_to_delete = db.session.query(Answer.id).filter(Answer.question_id == question_id).scalar_subquery()
    logger.info(f"[Master Task] Deleting ALL old ratings for Question ID: {question_id}.")
    Rating.query.filter(Rating.answer_id.in_(answer_ids_to_delete)).delete(synchronize_session=False)

    logger.info(f"[Master Task] Deleting ALL old answers for Question ID: {question_id}.")
    Answer.query.filter_by(question_id=question_id).delete(synchronize_session=False)
    
    db.session.commit()
    logger.info(f"[Master Task] Old data cleared successfully for Question ID: {question_id}.")
    
    rater_llms_all = LLM.query.filter(LLM.name.in_([rater for raters in RATERS.values() for rater in raters])).all()
    rater_ids_all = {rater.id for rater in rater_llms_all}
    logger.info(f"[Master Task] Rater model IDs to be excluded: {rater_ids_all}")

    llms_to_process = LLM.query.filter(LLM.id.notin_(rater_ids_all)).all()
    if not llms_to_process:
        logger.warning(f"[Master Task] No models to process for Question ID {question_id} after excluding raters.")
        return

    # from celery import group
    job = group(
        process_single_model.s(llm.id, question.id) for llm in llms_to_process
    )
    job.apply_async()
    
    logger.info(f"[Master Task] All sub-tasks for Question ID {question_id} have been queued for fresh generation.")
    
@celery.task
def process_single_model(model_id, question_id):
    logger.info(f"[Sub-Task] Started for Model ID: {model_id}, Question ID: {question_id}.")
    
    question = db.session.get(Question, question_id)
    llm = db.session.get(LLM, model_id)
    if not question or not llm:
        logger.error(f"[Sub-Task] Failed: Could not find Question {question_id} or LLM {model_id}.")
        return

    question_prompt = QUESTION_TEMPLATE[question.question_type].format(question.content)
    response_content = clients.generate_response(question_prompt, llm.id)
    
    answer = Answer(
        question_id=question.id,
        llm_id=llm.id,
        content=response_content
    )
    db.session.add(answer)
    db.session.commit()
    logger.info(f"[Sub-Task] Generated and saved Answer ID: {answer.id} for Model ID: {model_id}.")

    setting = Setting.query.filter_by(question_type=question.question_type).first()
    criteria = setting.criteria if setting else DEFAULT_CRITERIA[question.question_type]
    total_score = setting.total_score if setting else DEFAULT_TOTAL_SCORE
    
    rater_llms = LLM.query.filter(LLM.name.in_(RATERS[question.question_type])).all()
    rater_ids = [rater.id for rater in rater_llms]
    
    logger.info(f"[Sub-Task] Rating Answer ID: {answer.id} with raters: {[r.name for r in rater_llms]}.")
    
    # <-- 2. 调用从 utils 导入的函数 -->
    rate_answer(answer, question, criteria, total_score, rater_ids)
    
    db.session.commit()
    logger.info(f"[Sub-Task] Finished processing for Model ID: {model_id}, Question ID: {question_id}.")

# <-- 3. 删除本地的 rate_answer 函数 -->

@celery.task
def update_all_questions_for_model(model_id):
    """
    A Celery task to trigger updates for all questions for a specific model.
    """
    logger.info(f"--- [Model Update Task] Triggered for Model ID: {model_id} ---")
    
    question_ids = db.session.query(Question.id).all()
    if not question_ids:
        logger.warning(f"[Model Update Task] No questions found in the database. Nothing to do for Model ID: {model_id}.")
        return
        
    # Create a group of tasks to process each question for the given model
    job = group(
        process_single_model.s(model_id, q_id[0]) for q_id in question_ids
    )
    job.apply_async()
    
    logger.info(f"[Model Update Task] Queued {len(question_ids)} update sub-tasks for Model ID: {model_id}.")

@celery.task
def update_all_models_task():
    logger.info("--- [Scheduled Task] Updating all models for all questions ---")
    try:
        all_question_ids = [q.id for q in Question.query.with_entities(Question.id).all()]
        if not all_question_ids:
            logger.warning("[Scheduled Task] No questions found, skipping.")
            return
        
        job = group(
            process_question.s(qid) for qid in all_question_ids
        )
        job.apply_async()
            
        logger.info(f"[Scheduled Task] Successfully queued updates for {len(all_question_ids)} questions.")
    except Exception as e:
        logger.error(f"[Scheduled Task] Failed to queue update tasks: {e}", exc_info=True)
