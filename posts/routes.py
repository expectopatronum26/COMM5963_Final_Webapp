from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, url_for

from models import Favorite, Post, PostImage, ViewHistory, db
from . import posts_bp

CURRENT_USER_ID = 1
DEFAULT_IMAGE_URL = "https://picsum.photos/seed/roommate-default/900/600"


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


def _collect_image_urls(form):
    urls = []

    for value in form.getlist("image_urls"):
        value = (value or "").strip()
        if value:
            urls.append(value)

    extra_text = (form.get("image_urls_text") or "").strip()
    if extra_text:
        for line in extra_text.replace(",", "\n").splitlines():
            line = line.strip()
            if line:
                urls.append(line)

    unique_urls = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls


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
        is_favorite=favorite is not None,
    )


@posts_bp.route("/posts/new", methods=["GET", "POST"])
def new_post():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        rent = _to_decimal(request.form.get("rent"))
        location = (request.form.get("location") or "").strip()

        if not title or rent is None or not location:
            flash("标题、租金和位置为必填项")
            return render_template("posts/new.html", form=request.form), 400

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
            chore_distribution=(request.form.get("chore_distribution") or "").strip() or None,
            custom_requirements=(request.form.get("custom_requirements") or "").strip() or None,
        )
        db.session.add(post)
        db.session.flush()

        image_urls = _collect_image_urls(request.form)
        for index, image_url in enumerate(image_urls):
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

    return render_template("posts/new.html", form={})


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
