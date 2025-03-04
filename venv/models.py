from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
db=SQLAlchemy()
class Users(db.Model):
    _id = db.Column("id", db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    email = db.Column(db.String(100))
    password = db.Column(db.String(100))

    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password = password
class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    grade = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.now)
    original_pdf = db.Column(db.String(255))
    solution_pdf = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))