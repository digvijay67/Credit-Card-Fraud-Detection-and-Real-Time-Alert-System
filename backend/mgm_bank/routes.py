import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import select

from app import db
from app.behavior import transaction_features
from app.ml import MODEL_NAMES, predict
from app.models import Alert, Prediction, Transaction, User, utcnow
from app.routes import models, serialize_transaction

from .models import (
    MGMAccount,
    MGMBankTransaction,
    MGMLedgerEntry,
    MGMNotificationPreview,
)
from .service import ensure_customer_account

bank_api = Blueprint("mgm_bank_api", __name__)
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999.99")


def api_error(message, status):
    return jsonify({"error": message}), status


def active_user():
    return db.session.get(User, int(get_jwt_identity()))


def is_admin(user):
    return user is not None and user.role == "admin"


def iso(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def account_payload(account, user):
    customer = account.customer
    result = {
        "id": account.id,
        "bank_name": customer.bank_record.name,
        "bank_code": customer.bank_record.code,
        "environment": customer.bank_record.environment,
        "customer_id": customer.customer_id,
        "customer_name": customer.name,
        "email": customer.email,
        "mobile": customer.mobile,
        "account_number": account.account_number,
        "credit_limit": float(account.credit_limit),
        "used_limit": float(account.used_limit),
        "available_limit": float(account.credit_limit - account.used_limit),
        "status": account.status,
        "is_mine": customer.app_user_id == user.id,
    }
    if is_admin(user):
        result["owner_email"] = customer.app_user.email
    return result


def event_payload(event):
    prediction = event.fraud_transaction.prediction
    account = event.account
    customer = account.customer
    return {
        "id": event.id,
        "fraud_transaction_id": event.fraud_transaction_id,
        "customer_id": customer.customer_id,
        "customer_name": customer.name,
        "owner_email": customer.app_user.email,
        "amount": float(event.amount),
        "status": event.status,
        "classification": prediction.classification,
        "risk_score": prediction.risk_score,
        "model_name": prediction.model_name,
        "credit_limit": float(account.credit_limit),
        "used_limit": float(event.balance_after),
        "available_limit": float(account.credit_limit - event.balance_after),
        "created_at": iso(event.created_at),
    }


def replay_response(event, amount, occurred_at, distance, model_name):
    features = event.fraud_transaction.features
    prediction = event.fraud_transaction.prediction
    if (
        event.amount != amount
        or as_utc(event.fraud_transaction.occurred_at) != occurred_at
        or features.get("distance_from_last_km") != distance
        or prediction.model_name != model_name
    ):
        return api_error(
            "This idempotency key was already used for a different transaction.",
            409,
        )
    return jsonify({
        "transaction": serialize_transaction(event.fraud_transaction),
        "bank_transaction": event_payload(event),
        "idempotent_replay": True,
    })


def notification_payload(notification):
    return {
        "id": notification.id,
        "bank_transaction_id": notification.bank_transaction_id,
        "channel": notification.channel,
        "recipient": notification.recipient,
        "status": notification.status,
        "subject": notification.subject,
        "message": notification.message.replace(chr(36), "₹"),
        "created_at": iso(notification.created_at),
    }


def parse_transaction(body):
    try:
        amount = Decimal(str(body["amount"]))
        distance = float(body["distance_from_last_km"])
        raw_occurred_at = body["occurred_at"]
        if not isinstance(raw_occurred_at, str):
            raise ValueError
        occurred_at = datetime.fromisoformat(raw_occurred_at.replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            raise ValueError
        occurred_at = occurred_at.astimezone(timezone.utc)
        amount_in_cents = amount.quantize(CENT)
        if (
            not amount.is_finite()
            or amount <= 0
            or amount > MAX_AMOUNT
            or amount != amount_in_cents
            or not 0 <= distance <= 1_000_000_000
            or occurred_at > utcnow() + timedelta(minutes=5)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None, None, None, api_error(
            "Provide a positive amount with at most two decimals, a valid "
            "timezone-aware transaction time, and a non-negative distance.",
            400,
        )
    return amount_in_cents, distance, occurred_at, None


@bank_api.get("/accounts")
@jwt_required()
def accounts():
    user = active_user()
    if user is None:
        return api_error("Account not found", 401)

    if is_admin(user):
        rows = (
            MGMAccount.query.join(MGMAccount.customer)
            .order_by(MGMAccount.id)
            .all()
        )
    else:
        customer = ensure_customer_account(user)
        db.session.flush()
        rows = [customer.account]
    return jsonify([account_payload(row, user) for row in rows])


@bank_api.get("/transactions")
@jwt_required()
def transactions():
    user = active_user()
    if user is None:
        return api_error("Account not found", 401)
    query = MGMBankTransaction.query.join(MGMBankTransaction.account).join(
        MGMAccount.customer
    )
    if not is_admin(user):
        query = query.filter(MGMAccount.customer.has(app_user_id=user.id))
    rows = query.order_by(MGMBankTransaction.created_at.desc()).limit(200).all()
    return jsonify([event_payload(row) for row in rows])


@bank_api.get("/notifications")
@jwt_required()
def notifications():
    user = active_user()
    if user is None:
        return api_error("Account not found", 401)
    query = MGMNotificationPreview.query.join(
        MGMNotificationPreview.bank_transaction
    ).join(MGMBankTransaction.account).join(MGMAccount.customer)
    if not is_admin(user):
        query = query.filter(MGMAccount.customer.has(app_user_id=user.id))
    rows = query.order_by(MGMNotificationPreview.created_at.desc()).limit(100).all()
    return jsonify([notification_payload(row) for row in rows])


@bank_api.post("/transactions")
@jwt_required()
def create_bank_transaction():
    user = active_user()
    if user is None:
        return api_error("Account not found", 401)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return api_error("A JSON object is required", 400)

    amount, distance, occurred_at, validation_error = parse_transaction(body)
    if validation_error:
        return validation_error
    model_name = body.get("model", "xgboost")
    if model_name not in MODEL_NAMES:
        return api_error(f"model must be one of: {', '.join(MODEL_NAMES)}", 400)
    try:
        account_id = int(body["account_id"])
    except (KeyError, TypeError, ValueError):
        return api_error("A valid account_id is required", 400)
    idempotency_key = str(
        request.headers.get("Idempotency-Key", body.get("idempotency_key", ""))
    ).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
        return api_error("A valid Idempotency-Key is required", 400)

    account_query = MGMAccount.query.join(MGMAccount.customer).filter(
        MGMAccount.id == account_id
    )
    if not is_admin(user):
        account_query = account_query.filter(MGMAccount.customer.has(app_user_id=user.id))
    account = account_query.first()
    if account is None:
        return api_error("Bank account not found or access denied", 404)

    stored_key = f"{account.id}:{idempotency_key}"
    existing = MGMBankTransaction.query.filter_by(idempotency_key=stored_key).first()
    if existing is not None:
        return replay_response(existing, amount, occurred_at, distance, model_name)

    customer_user = account.customer.app_user
    features = transaction_features(customer_user.id, float(amount), occurred_at, distance)
    try:
        result = predict(models(), features, model_name)
    except FileNotFoundError as exception:
        current_app.logger.error("Prediction unavailable: %s", exception)
        return api_error(str(exception), 503)

    locked_account = db.session.execute(
        select(MGMAccount)
        .where(MGMAccount.id == account.id)
        .with_for_update()
    ).scalar_one_or_none()
    if locked_account is None or locked_account.status != "active":
        return api_error("Bank account is unavailable", 409)
    concurrent_replay = db.session.execute(
        select(MGMBankTransaction)
        .where(MGMBankTransaction.idempotency_key == stored_key)
        .with_for_update()
    ).scalar_one_or_none()
    if concurrent_replay is not None:
        return replay_response(
            concurrent_replay, amount, occurred_at, distance, model_name
        )

    used_before = Decimal(locked_account.used_limit).quantize(CENT)
    used_after = used_before
    if result["classification"] == "fraud":
        status = "fraud_hold"
    elif amount > Decimal(locked_account.credit_limit) - used_before:
        status = "declined_limit"
    else:
        status = "posted"
        used_after = used_before + amount

    transaction = Transaction(
        user_id=customer_user.id,
        amount=float(amount),
        occurred_at=occurred_at,
        features=features,
    )
    db.session.add(transaction)
    db.session.flush()
    prediction = Prediction(transaction_id=transaction.id, **result)
    db.session.add(prediction)
    db.session.flush()
    if status == "fraud_hold":
        severity = "high" if result["risk_score"] >= 80 else "medium"
        db.session.add(Alert(prediction_id=prediction.id, severity=severity))

    event = MGMBankTransaction(
        account_id=locked_account.id,
        fraud_transaction_id=transaction.id,
        idempotency_key=stored_key,
        amount=amount,
        status=status,
        balance_before=used_before,
        balance_after=used_after,
    )
    db.session.add(event)
    db.session.flush()
    if status == "posted":
        locked_account.used_limit = used_after
        db.session.add(
            MGMLedgerEntry(
                bank_transaction_id=event.id,
                entry_type="card_purchase",
                amount=amount,
                used_limit_before=used_before,
                used_limit_after=used_after,
            )
        )

    outcome = {
        "posted": "approved",
        "fraud_hold": "held for fraud review",
        "declined_limit": "declined because the available limit is insufficient",
    }[status]
    message = (
        f"MGM Bank demo transaction {transaction.id}: ₹{amount:.2f} {outcome}. "
        f"Risk score {result['risk_score']}/100. This is a local simulation; "
        "no real funds moved and no message was sent."
    )
    for channel, recipient in (
        ("email", account.customer.email),
        ("whatsapp", account.customer.mobile),
    ):
        db.session.add(
            MGMNotificationPreview(
                bank_transaction_id=event.id,
                channel=channel,
                recipient=recipient,
                status="preview_only",
                subject=f"MGM Bank demo transaction {status.replace('_', ' ')}",
                message=message,
            )
        )

    db.session.commit()
    return jsonify({
        "transaction": serialize_transaction(transaction),
        "bank_transaction": event_payload(event),
        "idempotent_replay": False,
    }), 201
