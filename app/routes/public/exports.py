from flask import Blueprint, send_file, current_app, abort, redirect, url_for, flash
from app.models import EvaluationHistory, Question
from app.core.report_export import export_report
from app.core.utils import convert_markdown_to_pdf, generate_leaderboard_data
from app.extensions import db
from app.config import EXPORTS_IMGS_DIR
from pathlib import Path

public_exports_bp = Blueprint('public_exports', __name__, url_prefix='/public')

@public_exports_bp.route('/export/report/<int:history_id>')
def export_report_history(history_id):
    """
    Export a report for a given history ID.
    This is a synchronous version for direct download.
    """
    try:
        from app.core.report_export import get_or_generate_report
        pdf_path = get_or_generate_report(history_id)
        if pdf_path:
            return send_file(pdf_path, as_attachment=True)
        else:
            flash('Failed to generate PDF report.', 'danger')
            return redirect(url_for('public_history.history_detail', history_id=history_id))

    except Exception as e:
        current_app.logger.error(f"Error exporting report for history_id {history_id}: {e}")
        flash("Error generating report.", 'danger')
        return redirect(url_for('public_history.history_detail', history_id=history_id))

@public_exports_bp.route('/export/leaderboard')
def export_leaderboard():
    """
    Export the latest history record report.
    Uses the same logic as history export: if PDF exists, use it;
    if not, convert from markdown; if no markdown, generate new report.
    """
    try:
        from app.core.report_export import get_or_generate_report

        # 获取最新的历史记录
        latest_history = EvaluationHistory.query.order_by(EvaluationHistory.timestamp.desc()).first()

        if not latest_history:
            current_app.logger.warning("No history records found, cannot export report")
            flash('没有找到历史记录，无法导出报告。', 'danger')
            return redirect(url_for('public_leaderboard.display_public_leaderboard'))

        current_app.logger.info(f"Exporting report for latest history record (ID: {latest_history.id})")

        # 使用与历史记录导出相同的逻辑
        pdf_path = get_or_generate_report(latest_history.id)

        if pdf_path:
            # 使用历史记录的时间戳作为文件名
            timestamp_str = latest_history.timestamp.strftime('%Y%m%d_%H%M%S')
            download_name = f"Report-{timestamp_str}.pdf"
            return send_file(pdf_path, as_attachment=True, download_name=download_name)
        else:
            flash('生成 PDF 报告失败。', 'danger')
            return redirect(url_for('public_leaderboard.display_public_leaderboard'))

    except Exception as e:
        current_app.logger.error(f"Error exporting leaderboard report: {e}", exc_info=True)
        flash("导出报告时发生错误。", 'danger')
        return redirect(url_for('public_leaderboard.display_public_leaderboard'))