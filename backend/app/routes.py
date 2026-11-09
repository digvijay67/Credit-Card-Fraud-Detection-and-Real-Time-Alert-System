import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from app import db, limiter
from app.behavior import transaction_features
from app.ml import MODEL_NAMES, evaluation_history, load_models, predict
from app.models import Alert, Prediction, Transaction, User, utcnow

api = Blueprint("api", __name__)
_models = None


def models():
    global _models
    if _models is None:
        _models = load_models()
    return _models


def error(message, status):
    return jsonify({"error": message}), status


def json_object():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def current_user():
    return db.session.get(User, int(get_jwt_identity()))


def admin_required():
    user = current_user()
    return user if user and user.role == "admin" else None


def utc_iso(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def serialize_transaction(transaction):
    prediction = transaction.prediction
    return {
        "id": transaction.id,
        "amount": transaction.amount,
        "occurred_at": utc_iso(transaction.occurred_at),
        "created_at": utc_iso(transaction.created_at),
        "prediction": None if prediction is None else {
            "model_name": prediction.model_name,
            "model_version": prediction.model_version,
            "fraud_probability": prediction.fraud_probability,
            "risk_score": prediction.risk_score,
            "classification": prediction.classification,
            "threshold": prediction.threshold,
            "explanation": prediction.explanation,
        },
    }


@api.post("/auth/register")
@limiter.limit("10 per hour")
def register():
    body = json_object()
    if body is None:
        return error("A JSON object is required", 400)
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    customer_name = body.get("customer_name")
    mobile = body.get("mobile")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return error("A valid email address is required", 400)
    if not isinstance(password, str) or len(password) < 12:
        return error("Password must contain at least 12 characters", 400)
    if customer_name is not None and (
        not isinstance(customer_name, str)
        or not 2 <= len(customer_name.strip()) <= 120
        or any(ord(character) < 32 for character in customer_name)
    ):
        return error("Customer name must contain 2 to 120 valid characters", 400)
    if mobile is not None and (
        not isinstance(mobile, str)
        or not re.fullmatch(r"\+?[0-9][0-9 ()-]{6,30}", mobile.strip())
    ):
        return error("Provide a valid mobile number", 400)
    if User.query.filter_by(email=email).first():
        return error("An account with this email already exists", 409)
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    from mgm_bank.service import ensure_customer_account

    db.session.flush()
    ensure_customer_account(
        user,
        customer_name=customer_name.strip() if customer_name else None,
        mobile=mobile.strip() if mobile else None,
    )
    db.session.commit()
    return jsonify({"id": user.id, "email": user.email, "role": user.role}), 201


@api.post("/auth/login")
@limiter.limit("10 per minute")
def login():
    from flask_jwt_extended import create_access_token

    body = json_object()
    if body is None:
        return error("A JSON object is required", 400)
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not isinstance(password, str) or not user.check_password(password):
        return error("Invalid email or password", 401)
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": {
        "id": user.id, "email": user.email, "role": user.role
    }})


@api.get("/auth/me")
@jwt_required()
def who_am_i():
    user = current_user()
    if user is None:
        return error("Account not found", 401)
    return jsonify({"user": {"id": user.id, "email": user.email, "role": user.role}})


@api.post("/transactions")
@jwt_required()
def create_transaction():
    body = json_object()
    if body is None:
        return error("A JSON object is required", 400)
    try:
        amount = float(body["amount"])
        if not 0 < amount <= 1_000_000_000:
            raise ValueError
        raw_occurred_at = body["occurred_at"]
        if not isinstance(raw_occurred_at, str):
            raise ValueError
        occurred_at = datetime.fromisoformat(raw_occurred_at.replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            raise ValueError
        occurred_at = occurred_at.astimezone(timezone.utc)
        if occurred_at > utcnow() + timedelta(minutes=5):
            raise ValueError
        distance = float(body["distance_from_last_km"])
        if not 0 <= distance <= 1_000_000_000:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return error(
            "Provide a positive amount, timezone-aware occurred_at no more than 5 minutes "
            "in the future, and a non-negative distance_from_last_km",
            400,
        )

    model_name = body.get("model", "xgboost")
    if model_name not in MODEL_NAMES:
        return error(f"model must be one of: {', '.join(MODEL_NAMES)}", 400)
    user_id = int(get_jwt_identity())
    features = transaction_features(user_id, amount, occurred_at, distance)
    try:
        result = predict(models(), features, model_name)
    except FileNotFoundError as exception:
        current_app.logger.error("Prediction unavailable: %s", exception)
        return error(str(exception), 503)

    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        occurred_at=occurred_at,
        features=features,
    )
    db.session.add(transaction)
    db.session.flush()
    prediction = Prediction(transaction_id=transaction.id, **result)
    db.session.add(prediction)
    db.session.flush()
    if result["classification"] == "fraud":
        severity = "high" if result["risk_score"] >= 80 else "medium"
        db.session.add(Alert(prediction_id=prediction.id, severity=severity))
    db.session.commit()
    return jsonify(serialize_transaction(transaction)), 201


@api.get("/transactions")
@jwt_required()
def transaction_history():
    user_id = int(get_jwt_identity())
    query = Transaction.query.filter_by(user_id=user_id)
    if current_user().role == "admin":
        query = Transaction.query
    rows = query.order_by(Transaction.created_at.desc()).limit(200).all()
    return jsonify([serialize_transaction(row) for row in rows])


@api.get("/admin/analytics")
@jwt_required()
def analytics():
    if not admin_required():
        return error("Administrator access required", 403)
    period = request.args.get("period", "daily")
    if period not in ("daily", "monthly"):
        return error("period must be 'daily' or 'monthly'", 400)
    days = 30 if period == "daily" else 365
    since = utcnow() - timedelta(days=days)
    total = Transaction.query.filter(Transaction.created_at >= since).count()
    fraud = Prediction.query.join(Transaction).filter(
        Transaction.created_at >= since, Prediction.classification == "fraud"
    ).count()
    date_bucket = (
        func.date_format(Transaction.created_at, "%Y-%m")
        if period == "monthly"
        else func.date(Transaction.created_at)
    )
    buckets = db.session.query(
        date_bucket, func.count(Transaction.id)
    ).filter(Transaction.created_at >= since).group_by(date_bucket).order_by(date_bucket).all()
    return jsonify({
        "period": period,
        "period_days": days,
        "total_transactions": total,
        "fraud_transactions": fraud,
        "genuine_transactions": total - fraud,
        "fraud_percentage": round(fraud * 100 / total, 2) if total else 0,
        "daily": [{"date": str(bucket), "transactions": count} for bucket, count in buckets],
    })


@api.get("/admin/model-comparison")
@jwt_required()
def model_comparison():
    if not admin_required():
        return error("Administrator access required", 403)
    return jsonify(evaluation_history())


@api.get("/admin/alerts")
@jwt_required()
def alerts():
    if not admin_required():
        return error("Administrator access required", 403)
    rows = Alert.query.order_by(Alert.created_at.desc()).limit(200).all()
    return jsonify([{
        "id": item.id,
        "transaction_id": item.prediction.transaction_id,
        "severity": item.severity,
        "status": item.status,
        "risk_score": item.prediction.risk_score,
        "created_at": utc_iso(item.created_at),
    } for item in rows])


@api.patch("/admin/alerts/<int:alert_id>")
@jwt_required()
def resolve_alert(alert_id):
    if not admin_required():
        return error("Administrator access required", 403)
    alert = db.session.get(Alert, alert_id)
    if alert is None:
        return error("Alert not found", 404)
    body = json_object()
    if body is None:
        return error("A JSON object is required", 400)
    if body.get("status") not in ("reviewed", "confirmed_fraud", "false_positive"):
        return error("Provide a valid alert status", 400)
    note = body.get("resolution_note", "")
    if not isinstance(note, str) or len(note) > 1000:
        return error("resolution_note must be 1000 characters or fewer", 400)
    alert.status = body["status"]
    alert.resolution_note = note
    alert.resolved_at = utcnow()
    db.session.commit()
    return jsonify({"id": alert.id, "status": alert.status})
