import logging
from app.extensions import db
from app.models import Question, Answer, Setting, LLM, Rating
from app.core.constants import DEFAULT_CRITERIA, QUESTION_TEMPLATE, RATERS, DEFAULT_TOTAL_SCORE
from app.core.llm import clients
from celery import Celery, group, chord
from celery.schedules import crontab
from celery.signals import after_setup_logger, worker_process_init
from app.core.utils import setup_logging, rate_answer, generate_leaderboard_data, convert_markdown_to_pdf
from app.core.report_export import export_report
import time
from pathlib import Path

logger = logging.getLogger('celery_tasks')

celery = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

_flask_app = None

celery.conf.beat_schedule = {
    'update-all-models-every-sunday': {
        'task': 'app.core.tasks.update_all_models_task',
        'schedule': crontab(hour=0, minute=0, day_of_week='sunday'), 
    },
}

@worker_process_init.connect
def init_worker(**kwargs):
    """Initialize Flask app once per worker process"""
    global _flask_app
    if _flask_app is None:
        logger.info("Initializing Flask app for worker process...")
        from app import create_app
        _flask_app = create_app()
        logger.info("Flask app initialized successfully for worker process.")

class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        global _flask_app
        if _flask_app is None:
            logger.warning("Flask app not initialized in worker, creating new instance...")
            from app import create_app
            _flask_app = create_app()

        with _flask_app.app_context():
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
    
    rate_answer(answer, question, criteria, total_score, rater_ids)
    
    db.session.commit()
    logger.info(f"[Sub-Task] Finished processing for Model ID: {model_id}, Question ID: {question_id}.")


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
        
    job = group(
        process_single_model.s(model_id, q_id[0]) for q_id in question_ids
    )
    job.apply_async()
    
    logger.info(f"[Model Update Task] Queued {len(question_ids)} update sub-tasks for Model ID: {model_id}.")

@celery.task
def update_all_models_task():
    """定时任务：更新所有模型对所有问题的回答，并在完成后保存历史记录"""
    logger.info("--- [Scheduled Task] Updating all models for all questions ---")
    try:
        all_question_ids = [q.id for q in Question.query.with_entities(Question.id).all()]
        if not all_question_ids:
            logger.warning("[Scheduled Task] No questions found, skipping.")
            return

        callback = save_evaluation_history_task.si()
        job = chord(
            (process_question.si(qid) for qid in all_question_ids),
            callback
        )
        job.apply_async()

        logger.info(f"[Scheduled Task] Successfully queued updates for {len(all_question_ids)} questions with history save callback.")
    except Exception as e:
        logger.error(f"[Scheduled Task] Failed to queue update tasks: {e}", exc_info=True)

@celery.task
def save_evaluation_history_task():
    """保存当前评估数据为历史记录（由定时任务完成后自动调用）"""
    logger.info("--- [History Save Task] Saving evaluation history snapshot ---")
    try:
        from app.models import EvaluationHistory

        current_data = generate_leaderboard_data()

        total_questions = Question.query.count()

        QUADRANT_SCORE_THRESHOLD = 3.0
        QUADRANT_RESPONSE_RATE_THRESHOLD = 50.0

        history_record = EvaluationHistory(
            dimensions=current_data['l1_dimensions'],
            evaluation_data=current_data['leaderboard'],
            extra_info={
                'score_threshold': QUADRANT_SCORE_THRESHOLD,
                'rate_threshold': QUADRANT_RESPONSE_RATE_THRESHOLD,
                'total_models': len(current_data['leaderboard']),
                'total_dimensions': len(current_data['l1_dimensions']),
                'total_questions': total_questions,
                'manual_save': False,
                'source': 'scheduled_task'
            }
        )
        db.session.add(history_record)
        db.session.commit()

        generate_and_save_reports.delay(history_record.id)

        logger.info(f"[History Save Task] Successfully saved evaluation history snapshot with {len(current_data['leaderboard'])} models and {total_questions} questions.")
        return {'success': True, 'models_count': len(current_data['leaderboard']), 'questions_count': total_questions}
    except Exception as e:
        logger.error(f"[History Save Task] Failed to save evaluation history: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}

@celery.task
def export_charts_task():
    """
    导出所有图表到exports/imgs文件夹的celery任务

    功能说明：
    1. 创建exports/imgs文件夹（如果不存在）
    2. 导出公共榜单的所有综合图表
    3. 导出每个模型的详细分析图表（model_detail页面中的图表）
    4. 导出偏见歧视分析表格

    如果安装了Playwright，将生成真实的图表截图
    否则创建占位符文件用于测试
    """
    from app.config import EXPORTS_IMGS_DIR

    logger.info("Chart export task started.")

    try:
        EXPORTS_IMGS_DIR.mkdir(parents=True, exist_ok=True)

        rater_names = [rater for raters in RATERS.values() for rater in raters]
        models = LLM.query.filter(LLM.name.notin_(rater_names)).all()

        if not models:
            logger.warning('No models found for chart export.')
            return {'success': False, 'message': '没有找到可导出的模型。', 'exported_count': 0}

        leaderboard_result = generate_leaderboard_data()
        leaderboard_data = leaderboard_result['leaderboard']
        l1_dims = leaderboard_result['l1_dimensions']

        timestamp = int(time.time())

        exported_count = export_all_charts(models, leaderboard_data, l1_dims, EXPORTS_IMGS_DIR, timestamp)

        logger.info(f"Successfully exported {exported_count} charts to {EXPORTS_IMGS_DIR}")
        return {
            'success': True,
            'message': f'成功导出了 {exported_count} 个图表到 {EXPORTS_IMGS_DIR} 文件夹。',
            'exported_count': exported_count
        }

    except Exception as e:
        logger.error(f"Error exporting charts in celery task: {e}", exc_info=True)
        return {
            'success': False,
            'message': '导出图表时发生错误，请检查日志。',
            'exported_count': 0
        }


@celery.task
def export_report_task(leaderboard_data: list = None, report_file_name: str = None, timestamp = None):
    """
    Celery task to export a report for given model_ids.
    """
    logger.info(f"Report export task started.")
    try:
        export_report(leaderboard_data=leaderboard_data, report_file_name=report_file_name, timestamp=timestamp)
        logger.info("Successfully exported report.")
        return {
            'success': True, 
            'message': f'成功导出了报告',
        }
    except Exception as e:
        logger.error(f"Error exporting report in celery task: {e}", exc_info=True)
        return {
            'success': False,
            'message': '导出报告时发生错误，请检查日志。'
        }

@celery.task
def generate_and_save_reports(history_id):
    """Generates and saves markdown and PDF reports for a given history record."""
    logger.info(f"--- [Report Generation Task] Started for History ID: {history_id} ---")
    try:
        from app.models import EvaluationHistory
        history = db.session.get(EvaluationHistory, history_id)
        if not history:
            logger.error(f"[Report Generation Task] Failed: Could not find History with ID {history_id}.")
            return

        markdown_path_str = export_report(
            leaderboard_data=[history.evaluation_data, history.dimensions],
            report_file_name=f"Report-{history.id}.md",
            timestamp=history.timestamp
        )
        history.markdown_report_path = markdown_path_str
        db.session.commit()
        logger.info(f"[Report Generation Task] Markdown report generated and path saved for History ID: {history_id}.")

        pdf_path = Path(markdown_path_str).with_suffix('.pdf')
        if convert_markdown_to_pdf(markdown_path_str, str(pdf_path)):
            history.pdf_report_path = str(pdf_path)
            db.session.commit()
            logger.info(f"[Report Generation Task] PDF report generated and path saved for History ID: {history_id}.")
        else:
            logger.error(f"[Report Generation Task] Failed to convert markdown to PDF for History ID: {history_id}.")

    except Exception as e:
        logger.error(f"[Report Generation Task] Error processing history ID {history_id}: {e}", exc_info=True)
