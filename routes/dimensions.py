from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from models import db, Dimension, Question

dimensions_bp = Blueprint('dimensions', __name__, url_prefix='/dimension')

@dimensions_bp.route('/manage', methods=['GET', 'POST'])
def manage_dimensions():
    # 获取所有维度数据，按层级组织
    level1_dims = Dimension.query.filter_by(level=1).all()
    level2_dims = Dimension.query.filter_by(level=2).all()
    level3_dims = Dimension.query.filter_by(level=3).all()
    
    # 组织维度数据用于前端展示
    dimension_tree = {}
    for dim1 in level1_dims:
        dimension_tree[dim1] = {}
        for dim2 in level2_dims:
            if dim2.parent == dim1.id:
                dimension_tree[dim1][dim2] = []
                for dim3 in level3_dims:
                    if dim3.parent == dim2.id:
                        dimension_tree[dim1][dim2].append(dim3)
    
    # 处理表单提交
    if request.method == 'POST':
        action = request.form.get('action')
        
        # 添加维度
        if action == 'add_dimension':
            dim_level = request.form.get('dim_level')
            
            if dim_level == '1':
                name = request.form.get('level1_name')
                if name:
                    new_dim = Dimension(name=name, level=1)
                    db.session.add(new_dim)
                    flash(f'一级维度 "{name}" 添加成功', 'success')
            
            elif dim_level == '2':
                parent_id = request.form.get('level1_id')
                name = request.form.get('level2_name')
                if parent_id and name:
                    new_dim = Dimension(name=name, level=2, parent=parent_id)
                    db.session.add(new_dim)
                    flash(f'二级维度 "{name}" 添加成功', 'success')
            
            elif dim_level == '3':
                parent_id = request.form.get('level2_id')
                name = request.form.get('level3_name')
                if parent_id and name:
                    new_dim = Dimension(name=name, level=3, parent=parent_id)
                    db.session.add(new_dim)
                    flash(f'三级维度 "{name}" 添加成功', 'success')
        
        # 删除维度
        elif action == 'delete_dimension':
            dim_id = request.form.get('dim_id')
            dim = Dimension.query.get(dim_id)
            if dim:
                # 检查是否有子维度或题目
                if dim.level == 1:
                    # 检查是否有子维度
                    children = Dimension.query.filter_by(parent=dim_id).all()
                    if children:
                        flash(f'无法删除一级维度"{dim.name}"，请先删除其下的二级维度', 'danger')
                        return redirect(url_for('dimensions.manage_dimensions'))
                
                elif dim.level == 2:
                    # 检查是否有子维度
                    children = Dimension.query.filter_by(parent=dim_id).all()
                    if children:
                        flash(f'无法删除二级维度"{dim.name}"，请先删除其下的三级维度', 'danger')
                        return redirect(url_for('dimensions.manage_dimensions'))
                    # 检查是否有题目
                    questions = Question.query.filter_by(dimension_id=dim_id).all()
                    if questions:
                        flash(f'无法删除二级维度"{dim.name}"，请先删除其下的题目', 'danger')
                        return redirect(url_for('dimensions.manage_dimensions'))
                
                elif dim.level == 3:
                    # 检查是否有题目
                    questions = Question.query.filter_by(dimension_id=dim_id).all()
                    if questions:
                        flash(f'无法删除三级维度"{dim.name}"，请先删除其下的题目', 'danger')
                        return redirect(url_for('dimensions.manage_dimensions'))
                
                # 删除维度
                db.session.delete(dim)
                flash(f'维度 "{dim.name}" 已删除', 'success')
        
        db.session.commit()
        return redirect(url_for('dimensions.manage_dimensions'))
    
    return render_template('dimensions.html', 
                        dimension_tree=dimension_tree,
                        level1_dims=level1_dims,
                        level2_dims=level2_dims,
                        level3_dims=level3_dims)

@dimensions_bp.route('/get')
def get_dimensions():
    level = request.args.get('level', type=int)
    parent_id = request.args.get('parent', type=int)
    
    if level == 2:
        # 获取一级维度的子维度（二级维度）
        dimensions = Dimension.query.filter_by(parent=parent_id, level=2).all()
    elif level == 3:
        # 获取二级维度的子维度（三级维度）
        dimensions = Dimension.query.filter_by(parent=parent_id, level=3).all()
    else:
        dimensions = []
    
    # 构建结果
    result = []
    for dim in dimensions:
        # 对于三级维度，添加父级信息
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