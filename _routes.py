from flask import render_template, request, redirect, url_for, jsonify, flash
from forms import QuestionForm, SettingForm, LLMForm
from models import db, Dimension, Question, Answer, Rating, Setting, LLM
from utils import process_question, process_all_questions
from sqlalchemy.orm import aliased
import threading
from config import DEFAULT_CRITERIA
from llm import clients

def register_routes(app):
        
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/dimensions', methods=['GET', 'POST'])
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
                            return redirect(url_for('manage_dimensions'))
                    
                    elif dim.level == 2:
                        # 检查是否有子维度
                        children = Dimension.query.filter_by(parent=dim_id).all()
                        if children:
                            flash(f'无法删除二级维度"{dim.name}"，请先删除其下的三级维度', 'danger')
                            return redirect(url_for('manage_dimensions'))
                        # 检查是否有题目
                        questions = Question.query.filter_by(dimension_id=dim_id).all()
                        if questions:
                            flash(f'无法删除二级维度"{dim.name}"，请先删除其下的题目', 'danger')
                            return redirect(url_for('manage_dimensions'))
                    
                    elif dim.level == 3:
                        # 检查是否有题目
                        questions = Question.query.filter_by(dimension_id=dim_id).all()
                        if questions:
                            flash(f'无法删除三级维度"{dim.name}"，请先删除其下的题目', 'danger')
                            return redirect(url_for('manage_dimensions'))
                    
                    # 删除维度
                    db.session.delete(dim)
                    flash(f'维度 "{dim.name}" 已删除', 'success')
            
            db.session.commit()
            return redirect(url_for('manage_dimensions'))
        
        return render_template('dimensions.html', 
                            dimension_tree=dimension_tree,
                            level1_dims=level1_dims,
                            level2_dims=level2_dims,
                            level3_dims=level3_dims)
        
    @app.route('/add_question', methods=['GET', 'POST'])
    def add_question():
        form = QuestionForm()
        
        # 获取所有维度数据
        level1_dims = Dimension.query.filter_by(level=1).all()
        level2_dims = Dimension.query.filter_by(level=2).all()
        level3_dims = Dimension.query.filter_by(level=3).all()
        
        # 组织维度数据用于前端展示
        dimension_options = {}
        for dim in level3_dims:
            level2 = dim.parent_ref
            level1 = level2.parent_ref if level2 else None
            
            if level1 and level2:
                level1_name = level1.name
                level2_name = level2.name
                level3_name = dim.name
                
                if level1_name not in dimension_options:
                    dimension_options[level1_name] = {}
                if level2_name not in dimension_options[level1_name]:
                    dimension_options[level1_name][level2_name] = []
                
                dimension_options[level1_name][level2_name].append((dim.id, level3_name))
        
        # 动态加载维度选择
        form.level1.choices = [(d.id, d.name) for d in level1_dims]
        form.level2.choices = [(d.id, d.name) for d in level2_dims]
        form.level3.choices = [(d.id, d.name) for d in level3_dims]
        
        if form.validate_on_submit():
            # 创建新问题
            new_question = Question(
                dimension_id=form.level3.data,
                question_type=form.question_type.data,
                content=form.content.data,
                answer=form.answer.data if form.question_type.data == 'objective' else None
            )
            db.session.add(new_question)
            db.session.commit()
            flash('题目添加成功', 'success')
            return redirect(url_for('index'))
        
        return render_template('add_question.html', form=form, dimension_options=dimension_options)

    @app.route('/update_questions', methods=['GET', 'POST'])
    def update_questions():
        if request.method == 'POST':
            question_id = request.form.get('question_id')
            if question_id:
                # 在后台线程中处理单个问题
                thread = threading.Thread(target=process_question, args=(question_id,))
                thread.start()
                return jsonify({'status': 'processing', 'question_id': question_id})
            else:
                # 处理所有问题
                thread = threading.Thread(target=process_all_questions)
                thread.start()
                return jsonify({'status': 'processing_all'})
        
        # 获取所有问题
        questions = Question.query.all()
        return render_template('update_questions.html', questions=questions)

    @app.route('/leaderboard')
    def leaderboard():
        # 获取筛选参数
        level1_id = request.args.get('level1')
        level2_id = request.args.get('level2')
        level3_id = request.args.get('level3')
        
        # 构建查询
        
        # 明确构建查询路径
        dim_level1 = aliased(Dimension)
        dim_level2 = aliased(Dimension)
        dim_level3 = aliased(Dimension)
        
    
        query = db.session.query(
            LLM.name.label('model_name'),
            db.func.avg(Rating.score).label('avg_score'),
            db.func.avg(Setting.total_score).label('avg_total')
        ).select_from(Answer)  # 明确指定查询起点
        # 添加连接
        query = query.join(LLM, Answer.llm_id == LLM.id)
        query = query.join(Question, Question.id == Answer.question_id)
        query = query.join(dim_level3, dim_level3.id == Question.dimension_id)
        query = query.join(Rating, Rating.answer_id == Answer.id)
        
        # 应用筛选条件
        if level3_id:
            query = query.filter(dim_level3.id == level3_id)
        elif level2_id:
            query = query.join(dim_level2, dim_level2.id == dim_level3.parent)
            query = query.filter(dim_level2.id == level2_id)
        elif level1_id:
            query = query.join(dim_level2, dim_level2.id == dim_level3.parent)
            query = query.join(dim_level1, dim_level1.id == dim_level2.parent)
            query = query.filter(dim_level1.id == level1_id)
        
        # 分组并排序
        leaderboard = query.group_by(LLM.name).order_by(db.desc('avg_score')).all()
        
        # 计算问题数量
        if level3_id:
            question_count = Question.query.filter_by(dimension_id=level3_id).count()
        elif level2_id:
            subquery = db.session.query(Dimension.id).filter_by(parent=level2_id)
            question_count = Question.query.filter(Question.dimension_id.in_(subquery)).count()
        elif level1_id:
            level2_ids = db.session.query(Dimension.id).filter_by(parent=level1_id)
            level3_ids = db.session.query(Dimension.id).filter(Dimension.parent.in_(level2_ids))
            question_count = Question.query.filter(Question.dimension_id.in_(level3_ids)).count()
        else:
            question_count = Question.query.count()
        
        # 获取维度数据用于筛选
        level1_dimensions = Dimension.query.filter_by(level=1).all()
        level2_dimensions = Dimension.query.filter_by(level=2).all()
        level3_dimensions = Dimension.query.filter_by(level=3).all()
        
        return render_template('leaderboard.html', 
                            leaderboard=leaderboard,
                            level1_dimensions=level1_dimensions,
                            level2_dimensions=level2_dimensions,
                            level3_dimensions=level3_dimensions,
                            question_count=question_count,
                            level1_id=level1_id,
                            level2_id=level2_id,
                            level3_id=level3_id)

    @app.route('/question/<int:question_id>')
    def question_detail(question_id):
        question = Question.query.get_or_404(question_id)
        answers = Answer.query.filter_by(question_id=question_id).options(
            db.joinedload(Answer.llm),
            db.joinedload(Answer.ratings).joinedload(Rating.llm)
        ).all()
        
        return render_template('question_detail.html', question=question, answers=answers)

    @app.route('/settings', methods=['GET', 'POST'])
    def settings():
        # 获取现有的评分标准
        objective_setting = Setting.query.filter_by(question_type='objective').first()
        subjective_setting = Setting.query.filter_by(question_type='subjective').first()
        
        # 处理表单提交
        form = SettingForm()
        if form.validate_on_submit():
            # 更新对应类型的评分标准
            setting = Setting.query.filter_by(question_type=form.question_type.data).first()
            if setting:
                setting.criteria = form.criteria.data
                setting.total_score = form.total_score.data  # 更新总分
            else:
                setting = Setting(
                    question_type=form.question_type.data,
                    criteria=form.criteria.data,
                    total_score=form.total_score.data  # 设置总分
                )
                db.session.add(setting)
            
            db.session.commit()
            return redirect(url_for('settings'))
        
        # 设置表单初始值
        form.question_type.data = 'objective'  # 默认显示客观题
        
        # 获取数据库中的评分标准
        objective_criteria = objective_setting.criteria if objective_setting else DEFAULT_CRITERIA['objective']
        subjective_criteria = subjective_setting.criteria if subjective_setting else DEFAULT_CRITERIA['subjective']
        
        # 获取总分值
        objective_total = objective_setting.total_score if objective_setting else 5.0
        subjective_total = subjective_setting.total_score if subjective_setting else 5.0
        
        # 设置初始值
        form.criteria.data = objective_criteria
        form.total_score.data = objective_total
        
        return render_template('settings.html', 
                            form=form,
                            objective_criteria=objective_criteria,
                            subjective_criteria=subjective_criteria,
                            objective_total=objective_total,
                            subjective_total=subjective_total)
        
    @app.route('/get_dimensions')
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
        
    @app.route('/model_management')
    def model_management():
        """模型管理页面"""
        llms = LLM.query.all()
        return render_template('model_management.html', llms=llms)

    @app.route('/add_model', methods=['GET', 'POST'])
    def add_model():
        """添加新模型"""
        form = LLMForm()
        # 确保至少有一个API密钥字段
        if not form.api_keys.entries:
            form.api_keys.append_entry()
        
        if form.validate_on_submit():
            # 处理API密钥列表
            api_keys = [key.data for key in form.api_keys if key.data.strip()]
            
            if not api_keys:
                flash('至少需要一个有效的API密钥', 'danger')
                return render_template('edit_model.html', form=form)
            
            new_llm = LLM(
                name=form.name.data,
                model=form.model.data,
                base_url=form.base_url.data,
                api_keys=api_keys,
            )
            db.session.add(new_llm)
            db.session.commit()
            
            llm = LLM.query.filter_by(name = form.name.data)
            clients.create_client(llm.id, llm.model, llm.base_url, llm.api_keys, llm.proxy)
            
            flash('模型添加成功', 'success')
            return redirect(url_for('model_management'))
        
        return render_template('edit_model.html', form=form, action='添加')

    @app.route('/edit_model/<int:model_id>', methods=['GET', 'POST'])
    def edit_model(model_id):
        """编辑现有模型"""
        llm = LLM.query.get_or_404(model_id)
        form = LLMForm(obj=llm)
        
        # 填充API密钥字段
        form.api_keys.entries = []  # 清空现有字段
        for key in llm.api_keys:
            form.api_keys.append_entry(key)
        
        # 确保至少有一个API密钥字段
        if not form.api_keys.entries:
            form.api_keys.append_entry()
        
        if form.validate_on_submit():
            # 处理API密钥列表
            api_keys = [key.data for key in form.api_keys if key.data.strip()]
            
            if not api_keys:
                flash('至少需要一个有效的API密钥', 'danger')
                return render_template('edit_model.html', form=form, action='编辑')
            
            llm.name = form.name.data
            llm.model = form.model.data
            llm.base_url = form.base_url.data
            llm.api_keys = api_keys
            
            clients.create_client(llm.id, llm.model, llm.base_url, llm.api_keys, llm.proxy)
            
            db.session.commit()
            flash('模型更新成功', 'success')
            return redirect(url_for('model_management'))
        
        return render_template('edit_model.html', form=form, action='编辑')

    @app.route('/delete_model/<int:model_id>', methods=['POST'])
    def delete_model(model_id):
        """删除模型"""
        llm = LLM.query.get_or_404(model_id)
        db.session.delete(llm)
        db.session.commit()
        flash(f'模型 {llm.name} 已删除', 'success')
        return redirect(url_for('model_management'))
