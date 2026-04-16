from flask import Blueprint

posts_bp = Blueprint("posts", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401
