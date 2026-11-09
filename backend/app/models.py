from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="user")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    features = db.Column(db.JSON, nullable=False)
    prediction = db.relationship("Prediction", backref="transaction", uselist=False)


class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(
        db.Integer, db.ForeignKey("transaction.id"), nullable=False, unique=True
    )
    model_name = db.Column(db.String(32), nullable=False)
    model_version = db.Column(db.String(64), nullable=False)
    fraud_probability = db.Column(db.Float, nullable=False)
    risk_score = db.Column(db.Integer, nullable=False)
    classification = db.Column(db.String(16), nullable=False, index=True)
    threshold = db.Column(db.Float, nullable=False)
    explanation = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prediction_id = db.Column(
        db.Integer, db.ForeignKey("prediction.id"), nullable=False, unique=True
    )
    severity = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="open")
    resolution_note = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    resolved_at = db.Column(db.DateTime(timezone=True))
    prediction = db.relationship("Prediction")
