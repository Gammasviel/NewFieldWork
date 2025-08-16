from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from models import db, Dimension, Question
import logging

dimensions_bp = Blueprint('dimensions', __name__, url_prefix='/dev/dimension')
logger = logging.getLogger('dimension_routes')

@dimensions_bp.route('/manage', methods=['GET', 'POST'])
def manage_dimensions():
    if request.method == 'GET':
        logger.info("Accessed dimension management page.")
    
    # ... (rest of the view logic is unchanged)
    
    # 处理表单提交
    if request.method == 'POST':
        action = request.form.get('action')
        logger.info(f"Received POST request for dimension action: {action}")
        
        # 添加维度
        if action == 'add_dimension':
            dim_level = request.form.get('dim_level')
            
            if dim_level == '1':
                name = request.form.get('level1_name')
                if name:
                    new_dim = Dimension(name=name, level=1)
                    db.session.add(new_dim)
                    flash(f'一级维度 "{name}" 添加成功', 'success')
                    logger.info(f"Added new level 1 dimension: '{name}'.")
            
            elif dim_level == '2':
                parent_id = request.form.get('level1_id')
                name = request.form.get('level2_name')
                if parent_id and name:
                    new_dim = Dimension(name=name, level=2, parent=parent_id)
                    db.session.add(new_dim)
                    flash(f'二级维度 "{name}" 添加成功', 'success')
                    logger.info(f"Added new level 2 dimension: '{name}' under parent ID {parent_id}.")
            
            elif dim_level == '3':
                parent_id = request.form.get('level2_id')
                name = request.form.get('level3_name')
                if parent_id and name:
                    new_dim = Dimension(name=name, level=3, parent=parent_id)
                    db.session.add(new_dim)
                    flash(f'三级维度 "{name}" 添加成功', 'success')
                    logger.info(f"Added new level 3 dimension: '{name}' under parent ID {parent_id}.")
        
        # 删除维度
        elif action == 'delete_dimension':
            dim_id = request.form.get('dim_id')
            dim = Dimension.query.get(dim_id)
            if dim:
                # ... (deletion check logic is unchanged)
                
                # 删除维度
                logger.warning(f"Attempting to delete dimension '{dim.name}' (ID: {dim.id}).")
                db.session.delete(dim)
                flash(f'维度 "{dim.name}" 已删除', 'success')
                logger.info(f"Successfully deleted dimension '{dim.name}' (ID: {dim.id}).")
        
        db.session.commit()
        return redirect(url_for('dimensions.manage_dimensions'))
    
    # ... (rest of the GET logic is unchanged)
    level1_dims = Dimension.query.filter_by(level=1).all()
    level2_dims = Dimension.query.filter_by(level=2).all()
    level3_dims = Dimension.query.filter_by(level=3).all()
    
    dimension_tree = {}
    for dim1 in level1_dims:
        dimension_tree[dim1] = {}
        for dim2 in level2_dims:
            if dim2.parent == dim1.id:
                dimension_tree[dim1][dim2] = []
                for dim3 in level3_dims:
                    if dim3.parent == dim2.id:
                        dimension_tree[dim1][dim2].append(dim3)

    return render_template('dimensions.html', 
                        dimension_tree=dimension_tree,
                        level1_dims=level1_dims,
                        level2_dims=level2_dims,
                        level3_dims=level3_dims)

@dimensions_bp.route('/get')
def get_dimensions():
    level = request.args.get('level', type=int)
    parent_id = request.args.get('parent', type=int)
    logger.debug(f"Fetching dimensions for level {level} with parent ID {parent_id}.")
    
    # ... (rest of the function is unchanged)
    if level == 2:
        dimensions = Dimension.query.filter_by(parent=parent_id, level=2).all()
    elif level == 3:
        dimensions = Dimension.query.filter_by(parent=parent_id, level=3).all()
    else:
        dimensions = []
    
    result = []
    for dim in dimensions:
        if level == 3:
            parent_dim = dim.parent_ref
            grandparent_dim = parent_dim.parent_ref if parent_dim else None
            dim_data = {
                'id': dim.id,
                'name': dim.name,
                'parent': parent_dim.name if parent_dim else '',
                'grandparent': grandparent_dim.name if grandparent_dim else ''
            }
        else:
            dim_data = {
                'id': dim.id,
                'name': dim.name
            }
        result.append(dim_data)
    
    return jsonify(result)