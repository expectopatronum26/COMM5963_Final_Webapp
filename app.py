import os
import sys
from pathlib import Path

from flask import Flask, redirect, url_for

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from models import db
from posts import posts_bp

app = Flask(__name__)
if load_dotenv:
    load_dotenv()

db_path = Path(app.instance_path) / 'flaskproject.db'
db_path.parent.mkdir(parents=True, exist_ok=True)

# SQLite itself has no charset setting; using an explicit file path avoids
# accidentally creating/reading a different database on Windows.
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path.as_posix()}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['JSON_AS_ASCII'] = False
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 6 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

db.init_app(app)
app.register_blueprint(posts_bp)

with app.app_context():
    db.create_all()


@app.route('/')
def hello_world():  # put application's code here
    return redirect(url_for('posts.list_posts'))


if __name__ == '__main__':
    app.run(debug=True)
