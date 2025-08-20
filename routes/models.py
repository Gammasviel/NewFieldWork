# .\routes\models.py
import os
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app
from werkzeug.utils import secure_filename
from models import db, LLM
from forms import LLMForm
from llm import clients
import logging

models_bp = Blueprint('models', __name__, url_prefix='/dev/model')
logger = logging.getLogger('model_routes')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

# Helper function to save icon
def save_icon(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'])
        os.makedirs(upload_path, exist_ok=True)
        file.save(os.path.join(upload_path, filename))
        return filename
    return None

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
        
        # Handle file upload
        icon_filename = None
        if 'icon' in request.files:
            file = request.files['icon']
            if file.filename != '':
                icon_filename = save_icon(file)

        new_llm = LLM(
            name=form.name.data, model=form.model.data,
            base_url=form.base_url.data, api_keys=api_keys,
            desc=form.desc.data, icon=icon_filename, comment=form.comment.data
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
            return render_template('edit_model.html', form=form, action='编辑')
        
        # Handle file upload for edit
        if 'icon' in request.files:
            file = request.files['icon']
            if file and file.filename != '':
                llm.icon = save_icon(file)

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
    
    return render_template('edit_model.html', form=form, action='编辑', llm=llm)



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