# .\tasks.py

import logging
from app import create_app
from models import db, Question, Answer, Setting, LLM, Rating # Ensure all models are imported
from config import DEFAULT_CRITERIA, QUESTION_TEMPLATE, RATING_TEMPLATE, RATERS, RATING_FAIL_RETRIES, DEFAULT_TOTAL_SCORE
from llm import clients
from celery import Celery, group
from celery.signals import after_setup_logger
from module_logger import setup_logging

logger = logging.getLogger('celery_tasks')

# --- Celery and Flask context boilerplate remains the same ---
flask_app = create_app()
celery = Celery(
    flask_app.import_name,
    backend=flask_app.config['CELERY_RESULT_BACKEND'],
    broker=flask_app.config['CELERY_BROKER_URL']
)
celery.conf.update(flask_app.config)

class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask
# --- End of boilerplate ---

# --- SOLUTION: Hook into Celery's logging setup ---
@after_setup_logger.connect
def setup_celery_logging(logger, **kwargs):
    """
    This function is called by the 'after_setup_logger' signal from Celery.
    It delegates the setup to our centralized setup_logging function.
    """
    # The 'logger' passed here is the root logger Celery is about to configure.
    # We ignore it and just call our main setup function, which gets the root
    # logger itself and configures it.
    setup_logging()
    logging.info("Celery worker logger configured.")
# --- END SOLUTION ---

@celery.task
def process_question(question_id):
    """
    MASTER TASK: Dispatches parallel sub-tasks for a single question.
    """
    logger.info(f"--- [Master Task] FORCING REGENERATION for Question ID: {question_id} ---")
    
    question = db.session.get(Question, question_id)
    if not question:
        logger.error(f"[Master Task] Failed: Could not find Question with ID {question_id}.")
        return

    # --- SOLUTION: Subquery-based Deletion Logic ---
    # 1. First, create a subquery to find all Answer IDs for the given question.
    answer_ids_to_delete = db.session.query(Answer.id).filter(Answer.question_id == question_id).scalar_subquery()

    # 2. Delete Ratings where the answer_id is in the subquery result.
    logger.info(f"[Master Task] Deleting ALL old ratings for Question ID: {question_id}.")
    # The .in_() operator works with the subquery.
    Rating.query.filter(Rating.answer_id.in_(answer_ids_to_delete)).delete(synchronize_session=False)

    # 3. Then, delete the old answers directly.
    logger.info(f"[Master Task] Deleting ALL old answers for Question ID: {question_id}.")
    Answer.query.filter_by(question_id=question_id).delete(synchronize_session=False)
    
    # 4. Commit the cleaning transaction.
    db.session.commit()
    logger.info(f"[Master Task] Old data cleared successfully for Question ID: {question_id}.")
    # --- Deletion Logic Ends ---
    
    # Get rater model IDs to exclude them from processing.
    rater_llms_all = LLM.query.filter(LLM.name.in_([rater for raters in RATERS.values() for rater in raters])).all()
    rater_ids_all = {rater.id for rater in rater_llms_all}
    logger.info(f"[Master Task] Rater model IDs to be excluded: {rater_ids_all}")

    # Get all non-rater LLMs to be evaluated.
    llms_to_process = LLM.query.filter(LLM.id.notin_(rater_ids_all)).all()
    if not llms_to_process:
        logger.warning(f"[Master Task] No models to process for Question ID {question_id} after excluding raters.")
        return

    # Create and execute the group of parallel sub-tasks.
    job = group(
        process_single_model.s(llm.id, question.id) for llm in llms_to_process
    )
    job.apply_async()
    
    logger.info(f"[Master Task] All sub-tasks for Question ID {question_id} have been queued for fresh generation.")
    
@celery.task
def process_single_model(model_id, question_id):
    """
    SUB-TASK: Generates an answer and gets it rated for ONE model.
    This task does the actual work in parallel with other similar tasks.
    """
    logger.info(f"[Sub-Task] Started for Model ID: {model_id}, Question ID: {question_id}.")
    
    question = db.session.get(Question, question_id)
    llm = db.session.get(LLM, model_id)
    if not question or not llm:
        logger.error(f"[Sub-Task] Failed: Could not find Question {question_id} or LLM {model_id}.")
        return

    # --- Generate a single answer ---
    question_prompt = QUESTION_TEMPLATE[question.question_type].format(question.content)
    response_content = clients.generate_response(question_prompt, llm.id)
    
    answer = Answer(
        question_id=question.id,
        llm_id=llm.id,
        content=response_content
    )
    db.session.add(answer)
    # We must commit here to get an answer.id for the rating step
    db.session.commit()
    logger.info(f"[Sub-Task] Generated and saved Answer ID: {answer.id} for Model ID: {model_id}.")

    # --- Rate the newly created answer ---
    setting = Setting.query.filter_by(question_type=question.question_type).first()
    criteria = setting.criteria if setting else DEFAULT_CRITERIA[question.question_type]
    total_score = setting.total_score if setting else DEFAULT_TOTAL_SCORE
    
    rater_llms = LLM.query.filter(LLM.name.in_(RATERS[question.question_type])).all()
    rater_ids = [rater.id for rater in rater_llms]
    
    logger.info(f"[Sub-Task] Rating Answer ID: {answer.id} with raters: {[r.name for r in rater_llms]}.")
    rate_answer(answer, question, criteria, total_score, rater_ids)
    
    # Final commit for the rating
    db.session.commit()
    logger.info(f"[Sub-Task] Finished processing for Model ID: {model_id}, Question ID: {question_id}.")


# This is now a helper function, not part of the main workflow logic
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
    else: # subjective
        rating_prompt = RATING_TEMPLATE['subjective'].format(
            question=question.content,
            criteria=criteria,
            response=answer.content
        )

    for rater_id in rater_ids:
        score = -1.0
        for i in range(RATING_FAIL_RETRIES):
            raw_score = clients.generate_response(rating_prompt, rater_id)
            try:
                parsed_score = float(raw_score)
                if 0 <= parsed_score <= total_score:
                    score = parsed_score
                    logger.info(f"Rater ID {rater_id} gave a valid score: {score} for Answer ID {answer.id}.")
                    break
                else:
                    logger.warning(f"Rater ID {rater_id} gave out-of-range score: {parsed_score}. Retrying... ({i+1}/{RATING_FAIL_RETRIES})")
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse score from rater ID {rater_id}. Raw: '{raw_score}'. Retrying... ({i+1}/{RATING_FAIL_RETRIES})")
        
        rater_llm = db.session.get(LLM, rater_id)
        rater_name = rater_llm.name if rater_llm else f"RaterID_{rater_id}"

        if score != -1.0:
            valid_scores.append(score)
        else:
            logger.error(f"Rating failed for Answer ID: {answer.id} by Rater '{rater_name}' after {RATING_FAIL_RETRIES} retries.")
        rater_comments.append(f'{rater_name}: {score if score != -1.0 else "Rating Failed"}')
    
    final_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    is_responsive = not (2.5 <= final_score <= 3.5)
    logger.info(f"Final score for Answer ID {answer.id} is {final_score:.2f}. Is responsive: {is_responsive}.")

    rating = Rating(
        answer_id=answer.id,
        llm_id=answer.llm_id, # The ID being rated, not the rater
        score=final_score,
        is_responsive=is_responsive,
        comment='\n'.join(rater_comments)
    )
    db.session.add(rating)