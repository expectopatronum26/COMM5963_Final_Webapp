import sys
import os
from pathlib import Path

from flask import Flask, redirect, url_for

from models import db
from posts import posts_bp

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
# Ensure an `instance/` folder inside the project root, cross-platform
db_path = os.path.join(basedir, 'instance', 'flaskproject.db')
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# SQLite itself has no charset setting; using an explicit file path avoids
# accidentally creating/reading a different database on Windows. Use POSIX
# style slashes in the URI to be safe on Windows.
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path.replace('\\', '/')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['JSON_AS_ASCII'] = False

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
