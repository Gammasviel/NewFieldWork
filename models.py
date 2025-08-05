from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy import PickleType

db = SQLAlchemy()

class Dimension(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    level = db.Column(db.Integer, nullable=False)  # 1, 2, or 3
    parent = db.Column(db.Integer, db.ForeignKey('dimension.id'))
    
    # 使用明确的relationship定义
    children = db.relationship(
        'Dimension', 
        backref=db.backref('parent_ref', remote_side=[id]),
        foreign_keys=[parent]
    )
    
    # 添加与Question的关系
    questions = db.relationship('Question', back_populates='dimension')
    
    def __repr__(self):
        return f'<Dimension {self.name} (Level {self.level})>'

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dimension_id = db.Column(db.Integer, db.ForeignKey('dimension.id'), nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # 'subjective' or 'objective'
    content = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text)  # Only for objective questions
    
    # 使用明确的relationship定义
    dimension = db.relationship(
        'Dimension', 
        back_populates='questions',
        foreign_keys=[dimension_id]
    )
    answers = db.relationship('Answer', back_populates='question', cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Question {self.id}: {self.content[:50]}>'

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    llm_id = db.Column(db.Integer, db.ForeignKey('llm.id'), nullable=False)  # 确保有这个字段
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    question = db.relationship('Question', back_populates='answers')
    ratings = db.relationship('Rating', back_populates='answer', cascade="all, delete-orphan")
    llm = db.relationship('LLM', backref='answers')  # 确保有这个关系
    
    def __repr__(self):
        return f'<Answer by {self.llm.name} for Q{self.question_id}>'

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(db.Integer, db.ForeignKey('answer.id'), nullable=False)
    llm_id = db.Column(db.Integer, db.ForeignKey('llm.id'), nullable=False)  # 改为关联LLM
    score = db.Column(db.Float, nullable=False)
    comment = db.Column(db.Text)
    is_responsive = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    answer = db.relationship('Answer', back_populates='ratings')
    llm = db.relationship('LLM', backref='ratings')  # 新增关系
    
    def __repr__(self):
        return f'<Rating {self.score} by {self.llm.name} for Answer {self.answer_id}>'

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_type = db.Column(db.String(20), nullable=False)  # 'subjective' or 'objective'
    criteria = db.Column(db.Text, nullable=False)
    total_score = db.Column(db.Float, nullable=False, default=5.0)
    last_updated = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<Setting ({self.question_type}): {self.criteria[:50]}>'

class LLM(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # 简称
    model = db.Column(db.String(100), nullable=False)  # API使用的模型全称
    base_url = db.Column(db.String(200), nullable=False)
    api_keys = db.Column(MutableList.as_mutable(PickleType), nullable=False)  # 多个API密钥列表
    proxy = db.Column(db.String(200), default = '')  # 代理地址
    
    def __repr__(self):
        return f'<LLM {self.name} ({self.model})>'