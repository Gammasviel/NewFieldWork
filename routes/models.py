# .\routes\models.py
import os
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app
# 1. 移除不再需要的 werkzeug 和 os
from models import LLM
from extensions import db
from forms import LLMForm
from llm import clients
import logging
# 2. 从 app 模块导入我们创建的 icons UploadSet
from extensions import icons

models_bp = Blueprint('models', __name__, url_prefix='/dev/model')
logger = logging.getLogger('model_routes')

@models_bp.route('/manage')
def model_management():
    logger.info("Accessed model management page.")
    llms = LLM.query.all()
    return render_template('model_management.html', llms=llms)

@models_bp.route('/add', methods=['GET', 'POST'])
def add_model():
    form = LLMForm()
    if not form.api_keys.entries:
        form.api_keys.append_entry()
    
    if form.validate_on_submit():
        logger.info(f"Attempting to add new model: {form.name.data}.")
        api_keys = [key.data for key in form.api_keys if key.data.strip()]
        
        if not api_keys:
            flash('至少需要一个有效的API密钥', 'danger')
            logger.warning("Add model failed: No valid API keys provided.")
            return render_template('edit_model.html', form=form)
        
        # 4. 使用 Flask-Uploads 保存文件
        icon_filename = None
        if 'icon' in request.files and request.files['icon'].filename != '':
            try:
                # icons.save() 会处理验证、生成安全唯一的文件名并保存
                icon_filename = icons.save(request.files['icon'])
            except Exception as e:
                flash(f'图标上传失败: {e}', 'danger')
                return render_template('edit_model.html', form=form, action='添加')

        new_llm = LLM(
            name=form.name.data, model=form.model.data,
            base_url=form.base_url.data, api_keys=api_keys,
            desc=form.desc.data, 
            icon=icon_filename,  # 保存由 Flask-Uploads 返回的新文件名
            comment=form.comment.data
        )
        db.session.add(new_llm)
        db.session.commit()
        logger.info(f"Successfully added model '{new_llm.name}' with ID {new_llm.id}.")
        
        clients.create_client(new_llm.id, new_llm.name, new_llm.model, new_llm.base_url, new_llm.api_keys, new_llm.proxy)
        
        flash('模型添加成功', 'success')
        return redirect(url_for('models.model_management'))
    
    return render_template('edit_model.html', form=form, action='添加')

@models_bp.route('/edit/<int:model_id>', methods=['GET', 'POST'])
def edit_model(model_id):
    llm = LLM.query.get_or_404(model_id)
    form = LLMForm(obj=llm)
    
    if request.method == 'GET':
        form.api_keys.entries = []
        for key in llm.api_keys:
            form.api_keys.append_entry(key)
        if not form.api_keys.entries:
            form.api_keys.append_entry()
            
    if form.validate_on_submit():
        logger.info(f"Attempting to update model ID: {model_id}.")
        api_keys = [key.data for key in form.api_keys if key.data.strip()]
        
        if not api_keys:
            flash('至少需要一个有效的API密钥', 'danger')
            logger.warning(f"Edit model ID {model_id} failed: No valid API keys provided.")
            return render_template('edit_model.html', form=form, action='编辑', llm=llm, icons=icons)
        
        # --- START: 修正逻辑 ---
        file_data = form.icon.data
        
        # 核心修正：检查 file_data 是否是文件对象（通过检查它是否有 filename 属性）
        # 并且确保文件名不为空，以防止空的上传字段。
        if file_data and hasattr(file_data, 'filename') and file_data.filename:
            logger.info(f"New icon file detected for model ID {model_id}: {file_data.filename}")
            try:
                # 删除旧图标 (可选，但推荐)
                if llm.icon:
                    try:
                        os.remove(icons.path(llm.icon))
                        logger.info(f"Removed old icon: {llm.icon}")
                    except OSError as e:
                        logger.warning(f"Could not remove old icon {llm.icon}: {e}")
                
                # 保存新图标
                llm.icon = icons.save(file_data)
                logger.info(f"Successfully saved new icon as: {llm.icon}")
            except Exception as e:
                logger.error(f"Icon upload failed for model ID {model_id}: {e}", exc_info=True)
                flash(f'图标上传失败: {e}', 'danger')
                return render_template('edit_model.html', form=form, action='编辑', llm=llm, icons=icons)
        else:
            # 如果没有新文件上传，则不执行任何图标操作，保留旧图标
            logger.info(f"No new icon file provided for model ID {model_id}. Keeping existing icon: {llm.icon}")
        # --- END: 修正逻辑 ---

        llm.name = form.name.data
        llm.model = form.model.data
        llm.base_url = form.base_url.data
        llm.api_keys = api_keys
        llm.desc = form.desc.data
        llm.comment = form.comment.data
        
        clients.create_client(llm.id, llm.name, llm.model, llm.base_url, llm.api_keys, llm.proxy)
        
        db.session.commit()
        flash('模型更新成功', 'success')
        logger.info(f"Successfully updated model '{llm.name}' (ID: {model_id}).")
        return redirect(url_for('models.model_management'))
    
    return render_template('edit_model.html', form=form, action='编辑', llm=llm, icons=icons)


@models_bp.route('/delete/<int:model_id>', methods=['POST'])
def delete_model(model_id):
    """删除模型"""
    llm = LLM.query.get_or_404(model_id)
    logger.warning(f"Attempting to delete model '{llm.name}' (ID: {model_id}).")
    db.session.delete(llm)
    db.session.commit()
    flash(f'模型 {llm.name} 已删除', 'success')
    logger.info(f"Successfully deleted model '{llm.name}' (ID: {model_id}).")
    return redirect(url_for('models.model_management'))