import os
import re
from html import escape
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from models import Favorite, Post, PostImage, ViewHistory, db
from . import posts_bp

CURRENT_USER_ID = 1
DEFAULT_IMAGE_URL = "https://picsum.photos/seed/roommate-default/900/600"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_CONTEXT_CHARS = 8000
AI_SYSTEM_PROMPT = """你是\"港硕找舍友\"平台的AI搜索助手。

你的任务：
- 根据用户的需求，从提供的房源列表中推荐最匹配的帖子
- 如果没有完全匹配的，推荐最接近的，并说明差异
- 如果完全没有相关房源，诚实告知，并建议用户调整条件

回答规则：
- 语言自适应：用户用什么语言提问，你就用什么语言回答
- 简洁友好，像朋友推荐房子一样
- 如果用户问的和找房无关，礼貌引导回找房话题
- 必须根据数据库内容如实作答，不要编造不存在的房源信息
- 推荐帖子时附上对应链接，方便用户直接跳转查看"""


def _current_user_id():
    return CURRENT_USER_ID


def _to_decimal(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _to_int(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_hobbies(value):
    hobbies_raw = value or ""
    hobbies_clean = re.sub(r"[，、\|/\s\.]+", ",", hobbies_raw)
    return re.sub(r",+", ",", hobbies_clean).strip(",")


def _delete_local_image_file(image_url):
    if not image_url or image_url.startswith("http://") or image_url.startswith("https://"):
        return

    relative_path = image_url.lstrip("/\\")
    absolute_path = os.path.abspath(os.path.join(current_app.root_path, relative_path.replace("/", os.sep)))
    uploads_root = os.path.abspath(os.path.join(current_app.root_path, "static", "uploads"))

    if os.path.commonpath([absolute_path, uploads_root]) != uploads_root:
        return

    if os.path.exists(absolute_path):
        os.remove(absolute_path)


def _serialize_post_for_chat(post):
    parts = [
        f"[ID:{post.id}] {post.title}",
        f"月租（HKD）:{post.rent}",
        f"地点:{post.location}",
        f"链接:/posts/{post.id}",
    ]
    if post.layout:
        parts.append(f"户型:{post.layout}")
    if post.nearby_school:
        parts.append(f"附近学校:{post.nearby_school}")
    if post.community_name:
        parts.append(f"小区:{post.community_name}")
    if post.poster_intro:
        parts.append(f"简介:{post.poster_intro}")
    if post.custom_requirements:
        parts.append(f"要求:{post.custom_requirements}")
    return " | ".join(parts)


def _build_context_with_limit(posts, max_chars):
    if max_chars <= 0:
        return ""

    lines = []
    used_chars = 0
    omitted_count = 0

    for post in posts:
        line = _serialize_post_for_chat(post)
        line_length = len(line) + (1 if lines else 0)
        if used_chars + line_length > max_chars:
            omitted_count += 1
            continue
        lines.append(line)
        used_chars += line_length

    context = "\n".join(lines)
    if omitted_count > 0:
        suffix = f"\n...已省略{omitted_count}条房源以控制上下文长度"
        allowed_suffix_len = max_chars - len(context)
        if allowed_suffix_len > 0:
            context += suffix[:allowed_suffix_len]

    return context


def _render_chat_answer_html(answer_text):
    import markdown

    text = answer_text or ""
    text = re.sub(r'(\S)\n(- )', r'\1\n\n\2', text)
    rendered_html = markdown.markdown(text)
    reference_pattern = re.compile(
        r"<a\b[^>]*\bhref=[\"'](?:/)?posts/(?P<a_id>\d+)[\"'][^>]*>.*?</a>"
        r"|(?P<path>(?:/)?posts/(?P<path_id>\d+))"
        r"|\[ID:(?P<bracket_id>\d+)\]"
        r"|\bID:(?P<id_only>\d+)\b",
        flags=re.IGNORECASE | re.DOTALL,
    )

    chunks = []
    last_index = 0
    for match in reference_pattern.finditer(rendered_html):
        chunks.append(rendered_html[last_index:match.start()])

        post_id = (
            match.group("a_id")
            or match.group("path_id")
            or match.group("bracket_id")
            or match.group("id_only")
        )
        chunks.append(f'<a href="/posts/{post_id}">点击查看帖子详情</a>')
        last_index = match.end()

    chunks.append(rendered_html[last_index:])
    final_html = "".join(chunks)
    return final_html


@posts_bp.route("/posts")
def list_posts():
    location = request.args.get("location", "").strip()
    nearby_school = request.args.get("nearby_school", "").strip()
    min_rent = _to_decimal(request.args.get("min_rent"))
    max_rent = _to_decimal(request.args.get("max_rent"))
    layout = request.args.get("layout", "").strip()

    query = Post.query.order_by(Post.created_at.desc())
    if location:
        query = query.filter(Post.location == location)
    if nearby_school:
        query = query.filter(Post.nearby_school == nearby_school)
    if min_rent is not None:
        query = query.filter(Post.rent >= min_rent)
    if max_rent is not None:
        query = query.filter(Post.rent <= max_rent)
    if layout:
        query = query.filter(Post.layout.contains(layout))

    posts = []
    for post in query.all():
        cover_image = post.images.order_by(PostImage.sort_order.asc(), PostImage.id.asc()).first()
        posts.append(
            {
                "post": post,
                "cover_url": cover_image.image_url if cover_image else DEFAULT_IMAGE_URL,
            }
        )

    return render_template(
        "posts/list.html",
        posts=posts,
        filters={
            "location": location,
            "nearby_school": nearby_school,
            "min_rent": request.args.get("min_rent", ""),
            "max_rent": request.args.get("max_rent", ""),
            "layout": layout,
        },
    )


@posts_bp.route("/posts/<int:post_id>")
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)

    history = ViewHistory(user_id=_current_user_id(), post_id=post.id)
    db.session.add(history)
    db.session.commit()

    images = post.images.order_by(PostImage.sort_order.asc(), PostImage.id.asc()).all()
    favorite = Favorite.query.filter_by(user_id=_current_user_id(), post_id=post.id).first()

    return render_template(
        "posts/detail.html",
        post=post,
        images=images,
        hobbies_json=post.hobbies or "[]",
        is_favorite=favorite is not None,
    )


@posts_bp.route("/posts/new", methods=["GET", "POST"])
def new_post():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        rent = _to_decimal(request.form.get("rent"))
        location = (request.form.get("location") or "").strip()
        uploaded_files = [
            file
            for file in request.files.getlist("images")
            if file and (file.filename or "").strip()
        ]
        allowed_extensions = {"jpg", "jpeg", "png", "webp"}

        if not title or rent is None or not location:
            flash("标题、月租和位置为必填项")
            return render_template("posts/new.html", form_data=request.form), 400

        if len(uploaded_files) > 6:
            flash("最多上传6张")
            return render_template("posts/new.html", form_data=request.form), 400

        hobbies_clean = _normalize_hobbies(request.form.get("hobbies", ""))

        post = Post(
            user_id=_current_user_id(),
            title=title,
            rent=rent,
            location=location,
            nearby_school=(request.form.get("nearby_school") or "").strip() or None,
            community_name=(request.form.get("community_name") or "").strip() or None,
            layout=(request.form.get("layout") or "").strip() or None,
            area=_to_decimal(request.form.get("area")),
            poster_gender=(request.form.get("poster_gender") or "").strip() or None,
            poster_age=_to_int(request.form.get("poster_age")),
            poster_occupation_or_school=(request.form.get("poster_occupation_or_school") or "").strip() or None,
            poster_intro=(request.form.get("poster_intro") or "").strip() or None,
            expected_schedule=(request.form.get("expected_schedule") or "").strip() or None,
            cleaning_frequency=(request.form.get("cleaning_frequency") or "").strip() or None,
            hobbies=hobbies_clean,
            custom_requirements=(request.form.get("custom_requirements") or "").strip() or None,
        )
        db.session.add(post)
        db.session.flush()

        upload_folder = current_app.config.get("UPLOAD_FOLDER") or os.path.join(
            current_app.root_path, "static", "uploads"
        )
        os.makedirs(upload_folder, exist_ok=True)

        saved_images = []
        for index, file in enumerate(uploaded_files):
            original_filename = file.filename or ""
            if "." not in original_filename:
                flash("只接受jpg/jpeg/png/webp格式")
                return render_template("posts/new.html", form_data = request.form), 400

            ext = original_filename.rsplit(".", 1)[1].lower()
            if ext not in allowed_extensions:
                flash("只接受jpg/jpeg/png/webp格式")
                return render_template("posts/new.html", form_data = request.form), 400

            # Keep backend validation aligned with frontend constraints.
            file.stream.seek(0, os.SEEK_END)
            file_size = file.stream.tell()
            file.stream.seek(0)
            if file_size > 5 * 1024 * 1024:
                flash("图片太大，请压缩后再上传")
                return render_template("posts/new.html", form_data=request.form), 400

            new_filename = secure_filename(f"{uuid4().hex}.{ext}")
            save_path = os.path.join(upload_folder, new_filename)
            file.save(save_path)
            saved_images.append((index, f"/static/uploads/{new_filename}"))

        for index, image_url in saved_images:
            db.session.add(
                PostImage(
                    post_id=post.id,
                    image_url=image_url,
                    sort_order=index,
                )
            )

        db.session.commit()
        flash("帖子发布成功")
        return redirect(url_for("posts.post_detail", post_id=post.id))

    return render_template("posts/new.html", form_data={})


@posts_bp.route("/posts/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    # TODO: 接入登录系统后，这里需要验证当前用户是否是发帖人

    image_records = post.images.all()
    image_urls = {image.image_url for image in image_records if image.image_url}

    for image_url in image_urls:
        _delete_local_image_file(image_url)

    db.session.delete(post)
    db.session.commit()
    flash("帖子已删除")
    return redirect(url_for("posts.list_posts"))


@posts_bp.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    # TODO: 接入登录系统后，这里需要验证当前用户是否是发帖人

    if request.method == "GET":
        return render_template("posts/edit.html", post=post, form_data={})

    title = (request.form.get("title") or "").strip()
    rent = _to_decimal(request.form.get("rent"))
    location = (request.form.get("location") or "").strip()
    uploaded_files = [
        file
        for file in request.files.getlist("images")
        if file and (file.filename or "").strip()
    ]
    delete_image_ids = {
        int(image_id)
        for image_id in request.form.getlist("delete_images")
        if (image_id or "").strip().isdigit()
    }
    allowed_extensions = {"jpg", "jpeg", "png", "webp"}
    existing_images = post.images.all()
    images_by_id = {image.id: image for image in existing_images}
    images_to_delete = [images_by_id[image_id] for image_id in delete_image_ids if image_id in images_by_id]
    remaining_image_count = len(existing_images) - len(images_to_delete)

    if not title or rent is None or not location:
        flash("标题、月租和位置为必填项")
        return render_template("posts/edit.html", post=post, form_data=request.form), 400

    if remaining_image_count + len(uploaded_files) > 6:
        flash("最多上传6张")
        return render_template("posts/edit.html", post=post, form_data=request.form), 400

    post.title = title
    post.rent = rent
    post.location = location
    post.nearby_school = (request.form.get("nearby_school") or "").strip() or None
    post.community_name = (request.form.get("community_name") or "").strip() or None
    post.layout = (request.form.get("layout") or "").strip() or None
    post.area = _to_decimal(request.form.get("area"))
    post.poster_gender = (request.form.get("poster_gender") or "").strip() or None
    post.poster_age = _to_int(request.form.get("poster_age"))
    post.poster_occupation_or_school = (
        (request.form.get("poster_occupation_or_school") or "").strip() or None
    )
    post.poster_intro = (request.form.get("poster_intro") or "").strip() or None
    post.expected_schedule = (request.form.get("expected_schedule") or "").strip() or None
    post.cleaning_frequency = (request.form.get("cleaning_frequency") or "").strip() or None
    post.hobbies = _normalize_hobbies(request.form.get("hobbies", ""))
    post.custom_requirements = (request.form.get("custom_requirements") or "").strip() or None

    for existing_image in images_to_delete:
        _delete_local_image_file(existing_image.image_url)
        db.session.delete(existing_image)

    if uploaded_files:
        upload_folder = current_app.config.get("UPLOAD_FOLDER") or os.path.join(
            current_app.root_path, "static", "uploads"
        )
        os.makedirs(upload_folder, exist_ok=True)

        saved_images = []
        for file in uploaded_files:
            original_filename = file.filename or ""
            if "." not in original_filename:
                flash("只接受jpg/jpeg/png/webp格式")
                return render_template("posts/edit.html", form_data = request.form), 400

            ext = original_filename.rsplit(".", 1)[1].lower()
            if ext not in allowed_extensions:
                flash("只接受jpg/jpeg/png/webp格式")
                return render_template("posts/edit.html", form_data = request.form), 400

            file.stream.seek(0, os.SEEK_END)
            file_size = file.stream.tell()
            file.stream.seek(0)
            if file_size > 5 * 1024 * 1024:
                flash("图片太大，请压缩后再上传")
                return render_template("posts/edit.html", post=post, form_data=request.form), 400

            new_filename = secure_filename(f"{uuid4().hex}.{ext}")
            save_path = os.path.join(upload_folder, new_filename)
            file.save(save_path)
            saved_images.append(f"/static/uploads/{new_filename}")

        remaining_images = [image for image in existing_images if image not in images_to_delete]
        max_sort_order = max([(image.sort_order or 0) for image in remaining_images], default=-1)

        for offset, image_url in enumerate(saved_images, start=1):
            db.session.add(
                PostImage(
                    post_id=post.id,
                    image_url=image_url,
                    sort_order=max_sort_order + offset,
                )
            )

    db.session.commit()
    flash("帖子更新成功")
    return redirect(url_for("posts.post_detail", post_id=post.id))


@posts_bp.route("/posts/<int:post_id>/favorite", methods=["POST"])
def toggle_favorite(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = _current_user_id()

    favorite = Favorite.query.filter_by(user_id=user_id, post_id=post.id).first()
    if favorite:
        db.session.delete(favorite)
        flash("已取消收藏")
    else:
        db.session.add(Favorite(user_id=user_id, post_id=post.id))
        flash("已加入收藏")

    db.session.commit()
    return redirect(url_for("posts.post_detail", post_id=post.id))


@posts_bp.route("/api/chat", methods=["POST"])
def chat_api():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message不能为空"}), 400

    if OpenAI is None:
        return jsonify({"error": "openai依赖未安装"}), 500

    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        return jsonify({"error": "DEEPSEEK_API_KEY未配置"}), 500

    posts = Post.query.order_by(Post.created_at.desc()).all()
    listings_context = _build_context_with_limit(posts, MAX_CONTEXT_CHARS)
    if not listings_context:
        listings_context = "当前数据库中暂无房源。"

    user_prompt = (
        "用户需求:\n"
        f"{message}\n\n"
        "房源列表(仅可基于以下内容回答):\n"
        f"{listings_context}"
    )

    try:
        client = OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=api_key)
        completion = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        answer = (completion.choices[0].message.content or "").strip()
        answer_html = _render_chat_answer_html(answer)
    except Exception:
        current_app.logger.exception("DeepSeek chat completion failed")
        return jsonify({"error": "AI服务暂时不可用，请稍后再试"}), 502

    return jsonify({"answer": answer, "answer_html": answer_html})


