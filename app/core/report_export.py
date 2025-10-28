import base64
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from app.core.llm import clients
from app.core.utils import generate_leaderboard_data, convert_markdown_to_pdf
from app.models import EvaluationHistory
from app.extensions import db
from app.config import EXPORTS_IMGS_DIR, EXPORTS_REPORTS_DIR

logger = logging.getLogger('report_export')

DATA_TEMPLATE = """各模型综合得分与相应率
模型,得分,相应率
{model_performance_rows}

各模型维度得分
模型,{dimension_names_header}
{dimension_scores_rows}

各模型题型数据
模型,客观题,主观题
{question_type_rows}

详细数据：
{json_data}"""

PROMPTS = [
    """请你结合四象限数据以及总得分和总响应率的两个表格数据，帮我分析总结论，参考样例如下“半数大模型内容安全鲁棒性较强，总得分在60%以上。综合总得分和总体响应率，部分大模型偏向粗放型安全管制”。输出的分析模板如下“总体大模型的安全鲁棒性情况+总得分情况介绍+总得分和总响应率分析”

注意，总得分越高表明安全鲁棒性越强，总响应率越高且总得分越高更好。
且输出的语言不要过于复杂，也不要字数过多，一两句话即可
仅输出分析，不输出其他内容，包括给出的分析的理由
要注意输出内容，不要太多零散的点，要是完整的段落和平滑的过渡
语言精炼且结论准确，且文字稳妥点，不要有太多评价，尤其是负面评价
且要注意用语去AI化
中文输出，一段话，一两句话即可，不需要输出分析过程，只需要最后给出的分析

{data_template}""",

    """请你结合各模型四大维度的平均得分对比表格数据，分析一下各大维度的大模型数据测评效果，输出样例参考如下“硬性法规约束强于软性价值约束。大模型在规避违法犯罪、规避信息失责方面表现较好，而在规避伦理失范、传播中国特色社会主义核心价值观的表现仍有一定提升空间。”输出的分析模板如下“在哪些维度表现得好+在哪些维度有提升空间+分析总体得分高的维度和得分低的维度呈现的特点”

注意，且输出的语言不要过于复杂，也不要字数过多，一两句话即可
仅输出分析，不输出其他内容，包括给出的分析的理由
要注意输出内容，不要太多零散的点，要是完整的段落和平滑的过渡
语言精炼且结论准确，且文字稳妥点，不要有太多评价，尤其是负面评价
且要注意用语去AI化
中文输出，一段话，一两句话即可，不需要输出分析过程，只需要最后给出的分析

{data_template}""",

    """请你结合各模型的客观题和主观题的平均得分对比的表格数据，分析一下各大模型测评效果，输出样例参考如下“表面上遵循公平公正，实际上存在内源性偏颇。多数大模型客观题得分远高于主观题得分，主要原因在于，不同题型下模型泛化能力不同。客观题，正确答案唯一确定，模型容易泛化；主观题，正确答案开放不定，且受到文化、社会和个人经验的影响，使得模型难以泛化，更容易表现出其训练数据中的偏见。。”输出的分析模板如下“大多数大模型的主观题和客观题哪一个得分更高+得分更高的原因+得分低的原因”

注意，输出的语言不要过于复杂，也不要字数过多
仅输出分析，不输出其他内容，包括给出的分析的理由
要注意输出内容，不要太多零散的点，要是完整的段落和平滑的过渡
语言精炼且结论准确，且文字稳妥点，不要有太多评价，尤其是负面评价
且要注意用语去AI化
中文输出，一段话，一两句话即可，不需要输出分析过程，只需要最后给出的分析

{data_template}"""
]

def get_image_base64(image_name: str) -> str:
    """
    Encodes an image to base64. If the specified image does not exist,
    it falls back to the first available image starting with image_name.
    """
    image_file = EXPORTS_IMGS_DIR / f"{image_name}.png"

    if not image_file.exists():
        logger.warning(f"Image '{image_name}.png' not found. Falling back to a default image.")
        try:
            fallback_file = sorted([img_f for img_f in os.listdir(EXPORTS_IMGS_DIR) if img_f.startswith(image_name)])[0]
            image_file = EXPORTS_IMGS_DIR / fallback_file
        except IndexError:
            logger.error(f"No fallback images found in '{EXPORTS_IMGS_DIR}'.")
            return ""

    with open(image_file, 'rb') as img:
        return base64.b64encode(img.read()).decode('utf-8')

def prepare_data_tables(leaderboard_data, dimension_metadata):
    """Prepares formatted string tables from leaderboard data."""
    model_performance_rows = []
    dimension_scores_rows = []
    question_type_rows = []

    dimension_names_header = ','.join([item['name'] for item in dimension_metadata])

    for item in leaderboard_data:
        model_performance_rows.append(','.join([item['name'], f"{item['avg_score'] / 5 * 100}%", f"{item['response_rate']}%" ]))
        dimension_scores_rows.append(','.join([item['name'], *[f"{jtem['avg'] / 5 * 100}%" for jtem in item['dim_scores'].values()]]))
        question_type_rows.append(','.join([item['name'], f"{item['avg_obj_score'] / 5 * 100}%", f"{item['avg_subj_score'] / 5 * 100}%" ]))

    return {
        "model_performance_rows": '\n'.join(model_performance_rows),
        "dimension_names_header": dimension_names_header,
        "dimension_scores_rows": '\n'.join(dimension_scores_rows),
        "question_type_rows": '\n'.join(question_type_rows)
    }

def generate_json_data(leaderboard_data, dimension_metadata):
    """Generates a JSON string with detailed leaderboard data."""
    dimension_id_to_name = {str(item["id"]): item["name"] for item in dimension_metadata}
    json_data = [
        {
            "模型名称": item['name'],
            "总得分": item['avg_score'] / 5 * 100,
            "响应率": item['response_rate'],
            "客观题得分": item['avg_obj_score'] / 5 * 100,
            "主观题得分": item['avg_subj_score'] / 5 * 100,
            "各维度数据": {
                dimension_id_to_name[str(dim_id)]: {
                    "得分": dim_data['avg'] / 5 * 100,
                    "响应率": dim_data['response_rate']
                }
                for dim_id, dim_data in item['dim_scores'].items()
            }
        }
        for item in leaderboard_data
    ]
    return json.dumps(json_data, ensure_ascii=False, indent=4)

def generate_llm_analysis(data_prompt):
    """Generates analysis text using the LLM."""
    analysis_texts = map(lambda prompt: clients.generate_response(prompt.format(data_template=data_prompt), 1), PROMPTS)
    return tuple(analysis_texts)

def encode_charts_to_base64():
    """Encodes the required chart images to base64."""
    chart_names = ['overall_bar_chart', 'quadrant_chart', 'dimension_bar_chart', 'question_type_bar_chart']
    encoded_charts = map(get_image_base64, chart_names)
    return tuple(encoded_charts)

def export_report(leaderboard_data: list = None, report_file_name: str = None, timestamp: datetime = None):
    """
    Generates and exports a report by preparing data, generating LLM analysis,
    and rendering it into a markdown template.
    """
    EXPORTS_REPORTS_DIR.mkdir(exist_ok=True, parents=True)

    if leaderboard_data is None:
        leaderboard_data, dimension_metadata = generate_leaderboard_data().values()
    else:
        leaderboard_data, dimension_metadata = leaderboard_data
    
    if report_file_name is None:
        report_file_name = f"Report {datetime.now().strftime('%Y-%m-%d %H-%M-%S')}.md"

    report_file_path = EXPORTS_REPORTS_DIR / report_file_name
    
    if timestamp is None:
        timestamp = datetime.now()
        
    compact_timestamp = timestamp.strftime('%m%d')
    full_timestamp = timestamp.strftime('%Y年%m月%d日')

    table_data = prepare_data_tables(leaderboard_data, dimension_metadata)
    json_data_str = generate_json_data(leaderboard_data, dimension_metadata)

    data_prompt = DATA_TEMPLATE.format(
        **table_data,
        json_data=json_data_str
    )

    overall_analysis_text, dimension_analysis_text, question_type_analysis_text = generate_llm_analysis(data_prompt)
    model_performance_chart_b64, quadrant_chart_b64, dimension_comparison_chart_b64, question_type_chart_b64 = encode_charts_to_base64()

    with open('./app/core/misc/export_template.md', 'r', encoding='utf-8') as f:
        export_template = f.read()

    report_content = export_template.format(
        overall_analysis_text=overall_analysis_text,
        dimension_analysis_text=dimension_analysis_text,
        question_type_analysis_text=question_type_analysis_text,
        compact_timestamp=compact_timestamp,
        full_timestamp=full_timestamp
    )

    report_content = report_content.replace('__MODEL_PERFORMANCE_CHART__', f'![模型综合性能分析](data:image/png;base64,{model_performance_chart_b64}){{ width=80% }}')
    report_content = report_content.replace('__QUADRANT_CHART__', f'![安全管制策略象限分析](data:image/png;base64,{quadrant_chart_b64}){{ width=80% }}')
    report_content = report_content.replace('__DIMENSION_COMPARISON_CHART__', f'![各模型维度平均分对比](data:image/png;base64,{dimension_comparison_chart_b64}){{ width=80% }}')
    report_content = report_content.replace('__QUESTION_TYPE_CHART__', f'![各模型题型分析](data:image/png;base64,{question_type_chart_b64}){{ width=80% }}')

    with open(report_file_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    logger.info(f"Report successfully exported to {report_file_path}")
    return str(report_file_path.resolve())

def check_and_export_charts_if_needed():
    """
    检查图表是否存在，如果不存在则导出图表。
    返回 True 表示图表已准备好，False 表示导出失败。
    """
    # 检查必需的图表文件是否存在
    required_charts = [
        'overall_bar_chart.png',
        'quadrant_chart.png',
        'dimension_bar_chart.png',
        'question_type_bar_chart.png'
    ]

    charts_exist = all((EXPORTS_IMGS_DIR / chart).exists() for chart in required_charts)

    if charts_exist:
        logger.info("All required charts already exist, skipping chart export.")
        return True

    # 图表不存在，需要导出
    logger.info("Required charts not found, exporting charts now...")
    try:
        from app.models import LLM
        from app.core.constants import RATERS
        from app.core.chart_export import export_all_charts
        import time

        EXPORTS_IMGS_DIR.mkdir(parents=True, exist_ok=True)

        # 获取当前排行榜数据
        current_data = generate_leaderboard_data()

        rater_names = [rater for raters in RATERS.values() for rater in raters]
        models = LLM.query.filter(LLM.name.notin_(rater_names)).all()

        timestamp = int(time.time())
        export_all_charts(
            models=models,
            leaderboard_data=current_data['leaderboard'],
            l1_dims=current_data['l1_dimensions'],
            imgs_dir=EXPORTS_IMGS_DIR,
            timestamp=timestamp,
            export_timestamp=False  # 使用固定文件名
        )

        logger.info("Charts exported successfully for history report.")
        return True
    except Exception as e:
        logger.error(f"Failed to export charts: {e}", exc_info=True)
        return False

def get_or_generate_report(history_id):
    history = EvaluationHistory.query.get_or_404(history_id)

    if history.pdf_report_path and os.path.exists(history.pdf_report_path):
        logger.info(f"PDF report for history {history_id} already exists. Sending file.")
        return history.pdf_report_path

    if history.markdown_report_path and os.path.exists(history.markdown_report_path):
        logger.info(f"Markdown report for history {history_id} exists. Converting to PDF.")
        pdf_path = Path(history.markdown_report_path).with_suffix('.pdf')
        if convert_markdown_to_pdf(history.markdown_report_path, str(pdf_path)):
            history.pdf_report_path = str(pdf_path)
            db.session.commit()
            return str(pdf_path)
        else:
            logger.error(f"Failed to convert markdown to PDF for history {history_id}.")
            return None

    # 导出历史记录报告前，检查并导出图表（如果需要）
    logger.info(f"No report found for history {history_id}. Checking charts availability...")
    if not check_and_export_charts_if_needed():
        logger.error(f"Failed to ensure charts are available for history {history_id}.")
        return None

    logger.info(f"Generating new report for history {history_id}.")
    markdown_path_str = export_report(
        leaderboard_data=[history.evaluation_data, history.dimensions],
        report_file_name=f"Report-{history.id}.md",
        timestamp=history.timestamp
    )
    history.markdown_report_path = markdown_path_str
    db.session.commit()

    pdf_path = Path(markdown_path_str).with_suffix('.pdf')
    if convert_markdown_to_pdf(markdown_path_str, str(pdf_path)):
        history.pdf_report_path = str(pdf_path)
        db.session.commit()
        return str(pdf_path)
    else:
        logger.error(f"Failed to convert markdown to PDF for history {history_id}.")
        return None