from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    avatar = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    identity_type = db.Column(db.String(20), nullable=False)  # 'student' or 'landlord'
    auth_photo = db.Column(db.String(255), nullable=True)
    auth_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    bio = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan")
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    messages_received = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='user', lazy='dynamic')
    favorites = db.relationship('Favorite', backref='user', lazy='dynamic')
    view_histories = db.relationship('ViewHistory', backref='user', lazy='dynamic')


class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    rent = db.Column(db.Numeric(10, 2), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    nearby_school = db.Column(db.String(100), nullable=True)
    community_name = db.Column(db.String(100), nullable=True)
    layout = db.Column(db.String(50), nullable=True)
    area = db.Column(db.Numeric(10, 2), nullable=True)
    cover_image = db.Column(db.String(500), nullable=True)
    
    # Poster details
    poster_gender = db.Column(db.String(10), nullable=True)
    poster_age = db.Column(db.Integer, nullable=True)
    poster_occupation_or_school = db.Column(db.String(100), nullable=True)
    poster_intro = db.Column(db.Text, nullable=True)
    hobbies = db.Column(db.Text, nullable=True)  # 存JSON格式的兴趣标签列表

    # Roommate expectations
    expected_schedule = db.Column(db.String(100), nullable=True)
    cleaning_frequency = db.Column(db.String(50), nullable=True)
    custom_requirements = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    images = db.relationship('PostImage', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    appointments = db.relationship('Appointment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    favorites = db.relationship('Favorite', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    view_histories = db.relationship('ViewHistory', backref='post', lazy='dynamic', cascade="all, delete-orphan")


class PostImage(db.Model):
    __tablename__ = 'post_images'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time_slot = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ViewHistory(db.Model):
    __tablename__ = 'view_histories'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

