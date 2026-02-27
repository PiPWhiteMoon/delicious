from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime

# 创建 Flask 应用
app = Flask(__name__)
# 允许跨域请求（方便开发时前后端分离）
CORS(app)

# 配置数据库：使用 SQLite，文件名为 database.db
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
db = SQLAlchemy(app)

# --------------------- 数据库模型 ---------------------
class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    abstract = db.Column(db.Text, default='')
    keywords = db.Column(db.String(200), default='')
    file_name = db.Column(db.String(200), default='')
    status = db.Column(db.String(20), default='submitted')  # submitted, accepted, rejected
    submitted_date = db.Column(db.String(10), default=lambda: datetime.now().strftime('%Y-%m-%d'))

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'abstract': self.abstract,
            'keywords': self.keywords,
            'file_name': self.file_name,
            'status': self.status,
            'submitted_date': self.submitted_date
        }

# 创建数据库表（如果不存在）
with app.app_context():
    db.create_all()

# --------------------- API 路由 ---------------------

# 首页：渲染前端页面
@app.route('/')
def index():
    return render_template('index.html')

# 获取所有稿件（按状态分类，方便前端直接渲染）
@app.route('/api/papers', methods=['GET'])
def get_papers():
    papers = Paper.query.all()
    return jsonify([p.to_dict() for p in papers])

# 投稿（创建新稿件）
@app.route('/api/papers', methods=['POST'])
def create_paper():
    data = request.get_json()
    # 简单校验
    if not data.get('title') or not data.get('author'):
        return jsonify({'error': '标题和作者不能为空'}), 400

    paper = Paper(
        title=data['title'],
        author=data['author'],
        abstract=data.get('abstract', ''),
        keywords=data.get('keywords', ''),
        file_name=data.get('file_name', ''),
        status='submitted'
    )
    db.session.add(paper)
    db.session.commit()
    return jsonify(paper.to_dict()), 201

# 更新稿件状态（接受/拒绝）
@app.route('/api/papers/<int:paper_id>', methods=['PUT'])
def update_paper(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    data = request.get_json()
    if 'status' in data and data['status'] in ['submitted', 'accepted', 'rejected']:
        paper.status = data['status']
        db.session.commit()
        return jsonify(paper.to_dict())
    return jsonify({'error': '无效的状态'}), 400

# 删除稿件
@app.route('/api/papers/<int:paper_id>', methods=['DELETE'])
def delete_paper(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    db.session.delete(paper)
    db.session.commit()
    return jsonify({'message': '删除成功'}), 200

# --------------------- 启动 ---------------------
if __name__ == '__main__':
    app.run(debug=True)