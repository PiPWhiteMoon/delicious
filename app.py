import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import oss2  # 阿里云 OSS SDK
from werkzeug.utils import secure_filename

# 创建 Flask 应用
app = Flask(__name__)
CORS(app)

# 配置密钥（用于 session）
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --------------------- 数据库模型 ---------------------
class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    abstract = db.Column(db.Text, default='')
    keywords = db.Column(db.String(200), default='')
    file_name = db.Column(db.String(200), default='')
    status = db.Column(db.String(20), default='submitted')
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

# 创建表
with app.app_context():
    db.create_all()

# --------------------- 阿里云OSS配置 ---------------------
# 从环境变量读取阿里云配置
ALI_ACCESS_KEY_ID = os.environ.get('ALI_ACCESS_KEY_ID')
ALI_ACCESS_KEY_SECRET = os.environ.get('ALI_ACCESS_KEY_SECRET')
ALI_BUCKET = os.environ.get('ALI_BUCKET')
ALI_REGION = os.environ.get('ALI_REGION')

if ALI_ACCESS_KEY_ID and ALI_ACCESS_KEY_SECRET and ALI_BUCKET and ALI_REGION:
    auth = oss2.Auth(ALI_ACCESS_KEY_ID, ALI_ACCESS_KEY_SECRET)
    # Endpoint 格式：http://oss-cn-region.aliyuncs.com
    endpoint = f'http://{ALI_REGION}.aliyuncs.com'
    bucket = oss2.Bucket(auth, endpoint, ALI_BUCKET)
    USE_OSS = True
else:
    USE_OSS = False
    print("警告: 阿里云OSS未配置，文件上传将只保存文件名，实际文件不会存储。")

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': '文件类型不允许，请上传 PDF、Word 或 TXT'}), 400

    if USE_OSS:
        try:
            # 上传到阿里云OSS
            bucket.put_object(file.filename, file.stream)
            # 生成文件访问 URL（如果存储桶是公共读）
            file_url = f"https://{ALI_BUCKET}.{ALI_REGION}.aliyuncs.com/{file.filename}"
            return jsonify({
                'success': True,
                'filename': file.filename,
                'file_url': file_url
            }), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        # 未配置OSS时，仅返回文件名（用于测试）
        return jsonify({
            'success': True,
            'filename': file.filename,
            'file_url': None
        }), 200

# --------------------- 公开接口（所有人能访问） ---------------------
# 1. 公开投稿接口
@app.route('/api/papers', methods=['POST'])
def create_paper():
    data = request.get_json()
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

# 2. 公开获取审核通过的文章（首页用）
@app.route('/api/papers/public', methods=['GET'])
def get_public_papers():
    # 只返回审核通过的文章，所有人能看
    papers = Paper.query.filter_by(status='accepted').all()
    return jsonify([p.to_dict() for p in papers])

# --------------------- 审稿人登录相关 ---------------------
# 给审稿密码加默认值（你可以直接改这里的123456）
REVIEWER_PASSWORD = os.environ.get('REVIEWER_PASSWORD', '123456')

@app.route('/reviewer/login', methods=['GET', 'POST'])
def reviewer_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == REVIEWER_PASSWORD:
            session['reviewer_logged_in'] = True
            return redirect(url_for('reviewer_dashboard'))
        else:
            return render_template('reviewer_login.html', error='密码错误')
    return render_template('reviewer_login.html')

@app.route('/reviewer/logout')
def reviewer_logout():
    session.pop('reviewer_logged_in', None)
    return redirect(url_for('reviewer_login'))

@app.route('/reviewer/dashboard')
def reviewer_dashboard():
    if not session.get('reviewer_logged_in'):
        return redirect(url_for('reviewer_login'))
    return render_template('reviewer_dashboard.html')

# --------------------- 审稿人专属API（需要登录） ---------------------
# 1. 审稿人看所有文章（待审核/已接受/已拒绝）
@app.route('/api/papers', methods=['GET'])
def get_papers():
    if not session.get('reviewer_logged_in'):
        return jsonify({'error': '请先以审稿人身份登录'}), 401
    papers = Paper.query.all()
    return jsonify([p.to_dict() for p in papers])

# 2. 审稿人修改文章状态（接受/拒绝）
@app.route('/api/papers/<int:paper_id>', methods=['PUT'])
def update_paper(paper_id):
    if not session.get('reviewer_logged_in'):
        return jsonify({'error': '请先以审稿人身份登录'}), 401
    paper = Paper.query.get_or_404(paper_id)
    data = request.get_json()
    if 'status' in data and data['status'] in ['submitted', 'accepted', 'rejected']:
        paper.status = data['status']
        db.session.commit()
        return jsonify(paper.to_dict())
    return jsonify({'error': '无效的状态'}), 400

# 3. 审稿人删除文章
@app.route('/api/papers/<int:paper_id>', methods=['DELETE'])
def delete_paper(paper_id):
    if not session.get('reviewer_logged_in'):
        return jsonify({'error': '请先以审稿人身份登录'}), 401
    paper = Paper.query.get_or_404(paper_id)
    db.session.delete(paper)
    db.session.commit()
    return jsonify({'message': '删除成功'}), 200

# --------------------- 首页 ---------------------
@app.route('/')
def index():
    return render_template('index.html')

# --------------------- 启动 ---------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
