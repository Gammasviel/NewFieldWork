from flask import Blueprint, redirect, url_for, flash, jsonify, send_file
import logging
import os
from pathlib import Path

from app.core.utils import convert_markdown_to_pdf
from app.core.report_export import export_report, get_or_generate_report
from app.models import EvaluationHistory
from app.extensions import db

exports_bp = Blueprint('exports', __name__, url_prefix='/dev/export')
logger = logging.getLogger('exports_routes')

@exports_bp.route('/reports', methods=['POST'])
def export_reports():
    """
    Exports the latest report as a PDF.
    """
    logger.info("Latest report export requested.")
    try:
        latest_history = EvaluationHistory.query.order_by(EvaluationHistory.timestamp.desc()).first()
        if not latest_history:
            flash('No history found to generate a report.', 'danger')
            return redirect(url_for('index.index'))

        pdf_path = get_or_generate_report(latest_history.id)
        if pdf_path:
            return send_file(pdf_path, as_attachment=True)
        else:
            flash('Failed to generate PDF report.', 'danger')
            return redirect(url_for('index.index'))

    except Exception as e:
        logger.error(f"Error exporting latest report: {e}", exc_info=True)
        flash('An error occurred while exporting the report.', 'danger')
        return redirect(url_for('index.index'))

@exports_bp.route('/history/<int:history_id>', methods=['POST'])
def export_history_report(history_id):
    """
    Exports a specific history report as a PDF.
    """
    logger.info(f"Report for history {history_id} requested.")
    try:
        pdf_path = get_or_generate_report(history_id)
        if pdf_path:
            return send_file(pdf_path, as_attachment=True)
        else:
            flash('Failed to generate PDF report.', 'danger')
            return redirect(url_for('dev_history.dev_history'))

    except Exception as e:
        logger.error(f"Error exporting history report {history_id}: {e}", exc_info=True)
        flash('An error occurred while exporting the report.', 'danger')
        return redirect(url_for('dev_history.dev_history'))

@exports_bp.route('/charts', methods=['POST'])
def export_all_charts():
    """
    Triggers the export of all charts as a background task.
    """
    logger.info("Export all charts requested.")
    try:
        from app.core.tasks import export_charts_task

        task = export_charts_task.delay()

        flash('图表导出任务已加入后台队列，请稍后查看 instance/exports/imgs 目录。', 'success')
        logger.info(f"Chart export task queued with ID: {task.id}")

    except Exception as e:
        logger.error(f"Error queuing chart export task: {e}", exc_info=True)
        flash('导出图表任务加入队列时发生错误，请检查 Celery 服务是否正常。', 'danger')

    return redirect(url_for('index.index'))