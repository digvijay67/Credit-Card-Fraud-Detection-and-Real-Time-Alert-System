from datetime import datetime, timedelta, timezone

import pytest

from app import create_app, db
from app.models import Transaction


@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "JWT_SECRET_KEY": "test-key-not-for-production",
        "RATELIMIT_ENABLED": False,
    })
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
        yield client
        with app.app_context():
            db.session.remove()
            db.drop_all()


def test_registration_rejects_weak_password(client):
    response = client.post("/api/auth/register", json={
        "email": "person@example.com",
        "password": "short",
    })
    assert response.status_code == 400


def test_registration_and_login(client):
    response = client.post("/api/auth/register", json={
        "email": "person@example.com",
        "password": "long-password-123",
        "customer_name": "Avery Morgan",
        "mobile": "+1-202-555-0142",
    })
    assert response.status_code == 201
    with client.application.app_context():
        from mgm_bank.models import MGMAccount, MGMCustomer

        customer = MGMCustomer.query.one()
        assert customer.name == "Avery Morgan"
        assert customer.email == "person@example.com"
        assert customer.mobile == "+1-202-555-0142"
        assert float(MGMAccount.query.one().credit_limit) == 5000.0
        assert customer.account.used_limit == 0
    response = client.post("/api/auth/login", json={
        "email": "person@example.com",
        "password": "long-password-123",
    })
    assert response.status_code == 200
    assert response.json["access_token"]


def test_registration_rejects_invalid_cardholder_details(client):
    response = client.post("/api/auth/register", json={
        "email": "person@example.com",
        "password": "long-password-123",
        "customer_name": "Avery",
        "mobile": "not-a-phone-number",
    })
    assert response.status_code == 400


def test_transaction_requires_authentication(client):
    response = client.post("/api/transactions", json={})
    assert response.status_code == 401


def test_transaction_derives_behavioral_features(client, monkeypatch):
    import app.routes as routes

    captured = []
    monkeypatch.setattr(routes, "models", lambda: {"xgboost": object()})

    def fake_predict(_models, features, _model_name):
        captured.append(features)
        return {
            "model_name": "xgboost",
            "model_version": "test",
            "fraud_probability": 0.1,
            "risk_score": 10,
            "classification": "genuine",
            "threshold": 0.5,
            "explanation": [],
        }

    monkeypatch.setattr(routes, "predict", fake_predict)
    client.post("/api/auth/register", json={
        "email": "person@example.com",
        "password": "long-password-123",
    })
    login = client.post("/api/auth/login", json={
        "email": "person@example.com",
        "password": "long-password-123",
    })
    headers = {"Authorization": f"Bearer {login.json['access_token']}"}

    first_time = datetime.now(timezone.utc)
    first = client.post("/api/transactions", headers=headers, json={
        "amount": 100,
        "occurred_at": first_time.isoformat(),
        "distance_from_last_km": 0,
    })
    assert first.status_code == 201
    assert captured[0]["transactions_last_24h"] == 0
    assert captured[0]["avg_amount_30d"] == 0

    second = client.post("/api/transactions", headers=headers, json={
        "amount": 250,
        "occurred_at": (first_time + timedelta(seconds=1)).isoformat(),
        "distance_from_last_km": 12,
    })
    assert second.status_code == 201
    assert captured[1]["transactions_last_24h"] == 1
    assert captured[1]["avg_amount_30d"] == 100


def test_transaction_returns_service_unavailable_without_model(client, monkeypatch):
    import app.routes as routes

    monkeypatch.setattr(routes, "models", lambda: {})
    token = client.post("/api/auth/register", json={
        "email": "person@example.com",
        "password": "long-password-123",
    })
    assert token.status_code == 201
    login = client.post("/api/auth/login", json={
        "email": "person@example.com",
        "password": "long-password-123",
    })
    response = client.post("/api/transactions", headers={
        "Authorization": f"Bearer {login.json['access_token']}",
    }, json={
        "amount": 42,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "distance_from_last_km": 4,
    })
    assert response.status_code == 503
    with client.application.app_context():
        assert Transaction.query.count() == 0


def test_fraud_prediction_creates_an_alert(client, monkeypatch):
    import app.routes as routes
    from app.models import Alert

    monkeypatch.setattr(routes, "models", lambda: {"xgboost": object()})
    monkeypatch.setattr(routes, "predict", lambda *_args: {
        "model_name": "xgboost",
        "model_version": "test",
        "fraud_probability": 0.92,
        "risk_score": 92,
        "classification": "fraud",
        "threshold": 0.5,
        "explanation": [],
    })
    client.post("/api/auth/register", json={
        "email": "person@example.com",
        "password": "long-password-123",
    })
    login = client.post("/api/auth/login", json={
        "email": "person@example.com",
        "password": "long-password-123",
    })
    response = client.post("/api/transactions", headers={
        "Authorization": f"Bearer {login.json['access_token']}",
    }, json={
        "amount": 42,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "distance_from_last_km": 4,
    })
    assert response.status_code == 201
    with client.application.app_context():
        alert = Alert.query.one()
        assert alert.severity == "high"
        assert alert.prediction.transaction_id == response.json["id"]


def test_admin_dashboard_counts_fraud_and_genuine_predictions(client, monkeypatch):
    import app.routes as routes

    monkeypatch.setattr(routes, "models", lambda: {
        "xgboost": object(),
        "random_forest": object(),
        "logistic_regression": object(),
    })

    def fake_predict(_models, features, model_name):
        suspicious = features["amount"] > 1000
        risk = 95 if suspicious else 5
        return {
            "model_name": model_name,
            "model_version": "test",
            "fraud_probability": risk / 100,
            "risk_score": risk,
            "classification": "fraud" if suspicious else "genuine",
            "threshold": 0.5,
            "explanation": [],
        }

    monkeypatch.setattr(routes, "predict", fake_predict)
    client.post("/api/auth/register", json={
        "email": "admin@example.com",
        "password": "long-password-123",
    })
    with client.application.app_context():
        from app.models import User

        User.query.filter_by(email="admin@example.com").one().role = "admin"
        db.session.commit()
    headers = register_and_login(client, "admin@example.com")

    for model_name, amount, expected in (
        ("xgboost", 145.50, "genuine"),
        ("random_forest", 2500, "fraud"),
        ("logistic_regression", 45, "genuine"),
    ):
        response = client.post("/api/transactions", headers=headers, json={
            "amount": amount,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "distance_from_last_km": 8,
            "model": model_name,
        })
        assert response.status_code == 201
        assert response.json["prediction"]["classification"] == expected

    dashboard = client.get("/api/admin/analytics", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json["total_transactions"] == 3
    assert dashboard.json["fraud_transactions"] == 1
    assert dashboard.json["genuine_transactions"] == 2
    assert dashboard.json["fraud_percentage"] == pytest.approx(33.33)


def test_model_comparison_is_admin_only_and_includes_all_models(client, monkeypatch):
    import app.routes as routes
    from app.models import User

    metrics = [
        {"model_name": name, "metrics": {"accuracy": 0.9}}
        for name in ("random_forest", "xgboost", "logistic_regression")
    ]
    monkeypatch.setattr(routes, "evaluation_history", lambda: metrics)
    user_headers = register_and_login(client, "comparison@example.com")

    assert client.get("/api/admin/model-comparison").status_code == 401
    assert client.get(
        "/api/admin/model-comparison", headers=user_headers
    ).status_code == 403
    with client.application.app_context():
        User.query.filter_by(email="comparison@example.com").one().role = "admin"
        db.session.commit()

    response = client.get("/api/admin/model-comparison", headers=user_headers)
    assert response.status_code == 200
    assert {row["model_name"] for row in response.json} == {
        "random_forest", "xgboost", "logistic_regression"
    }


def register_and_login(client, email="person@example.com"):
    client.post("/api/auth/register", json={
        "email": email,
        "password": "long-password-123",
    })
    response = client.post("/api/auth/login", json={
        "email": email,
        "password": "long-password-123",
    })
    return {"Authorization": f"Bearer {response.json['access_token']}"}


def bank_prediction(classification="genuine", risk_score=5, model_name="xgboost"):
    return {
        "model_name": model_name,
        "model_version": "test",
        "fraud_probability": risk_score / 100,
        "risk_score": risk_score,
        "classification": classification,
        "threshold": 0.5,
        "explanation": [],
    }


def test_bank_purchase_is_atomic_and_idempotent(client, monkeypatch):
    from app import db
    import app.routes as routes
    import mgm_bank.routes as bank_routes
    from mgm_bank.models import MGMBankTransaction, MGMLedgerEntry, MGMNotificationPreview

    captured = []
    monkeypatch.setattr(routes, "models", lambda: {
        "xgboost": object(),
        "random_forest": object(),
        "logistic_regression": object(),
    })
    monkeypatch.setattr(bank_routes, "models", lambda: {
        "xgboost": object(),
        "random_forest": object(),
        "logistic_regression": object(),
    })
    monkeypatch.setattr(
        bank_routes, "predict", lambda _models, features, _name: (
            captured.append(features)
            or bank_prediction(model_name="logistic_regression")
        )
    )
    headers = register_and_login(client)
    account = client.get("/api/bank/accounts", headers=headers).json[0]
    occurred_at = datetime.now(timezone.utc).isoformat()
    request_body = {
        "account_id": account["id"],
        "amount": "125.50",
        "occurred_at": occurred_at,
        "distance_from_last_km": 4,
        "model": "logistic_regression",
        "idempotency_key": "test-purchase-0001",
    }

    response = client.post("/api/bank/transactions", headers=headers, json=request_body)
    assert response.status_code == 201
    assert response.json["bank_transaction"]["status"] == "posted"
    assert response.json["bank_transaction"]["used_limit"] == 125.5

    replay = client.post("/api/bank/transactions", headers=headers, json=request_body)
    assert replay.status_code == 200
    assert replay.json["idempotent_replay"] is True
    notifications = client.get("/api/bank/notifications", headers=headers)
    assert notifications.status_code == 200
    assert len(notifications.json) == 2
    assert all("₹125.50" in item["message"] for item in notifications.json)
    with client.application.app_context():
        event = MGMBankTransaction.query.one()
        assert event.amount == 125.5
        assert MGMLedgerEntry.query.count() == 1
        assert MGMNotificationPreview.query.count() == 2
        assert {item.channel for item in MGMNotificationPreview.query.all()} == {
            "email", "whatsapp"
        }
        for preview in MGMNotificationPreview.query.all():
            preview.message = preview.message.replace("₹", "$")
        db.session.commit()
    legacy_notifications = client.get("/api/bank/notifications", headers=headers)
    assert legacy_notifications.status_code == 200
    assert all("₹125.50" in item["message"] for item in legacy_notifications.json)
    assert all("$" not in item["message"] for item in legacy_notifications.json)
    assert captured[0]["transactions_last_24h"] == 0


def test_bank_fraud_transaction_is_held_without_ledger_debit(client, monkeypatch):
    import app.routes as routes
    import mgm_bank.routes as bank_routes
    from mgm_bank.models import MGMBankTransaction, MGMLedgerEntry, MGMNotificationPreview
    from app.models import Alert

    monkeypatch.setattr(routes, "models", lambda: {"xgboost": object()})
    monkeypatch.setattr(bank_routes, "models", lambda: {"xgboost": object()})
    monkeypatch.setattr(
        bank_routes, "predict", lambda *_args: bank_prediction("fraud", 92)
    )
    headers = register_and_login(client)
    account = client.get("/api/bank/accounts", headers=headers).json[0]
    response = client.post("/api/bank/transactions", headers=headers, json={
        "account_id": account["id"],
        "amount": "80.00",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "distance_from_last_km": 4,
        "idempotency_key": "test-fraud-0001",
    })
    assert response.status_code == 201
    assert response.json["bank_transaction"]["status"] == "fraud_hold"
    assert response.json["bank_transaction"]["used_limit"] == 0
    with client.application.app_context():
        assert MGMBankTransaction.query.one().status == "fraud_hold"
        assert MGMLedgerEntry.query.count() == 0
        assert MGMNotificationPreview.query.count() == 2
        assert Alert.query.count() == 1


def test_bank_transaction_declines_when_limit_is_exceeded(client, monkeypatch):
    import app.routes as routes
    import mgm_bank.routes as bank_routes
    from mgm_bank.models import MGMAccount, MGMLedgerEntry

    monkeypatch.setattr(routes, "models", lambda: {"xgboost": object()})
    monkeypatch.setattr(bank_routes, "models", lambda: {"xgboost": object()})
    monkeypatch.setattr(bank_routes, "predict", lambda *_args: bank_prediction())
    headers = register_and_login(client)
    account = client.get("/api/bank/accounts", headers=headers).json[0]
    with client.application.app_context():
        account_row = db.session.get(MGMAccount, account["id"])
        account_row.credit_limit = 50
        db.session.commit()

    response = client.post("/api/bank/transactions", headers=headers, json={
        "account_id": account["id"],
        "amount": "50.01",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "distance_from_last_km": 4,
        "idempotency_key": "test-limit-0001",
    })
    assert response.status_code == 201
    assert response.json["bank_transaction"]["status"] == "declined_limit"
    assert response.json["bank_transaction"]["used_limit"] == 0
    with client.application.app_context():
        assert MGMLedgerEntry.query.count() == 0


def test_bank_account_isolation(client, monkeypatch):
    import app.routes as routes
    from mgm_bank.models import MGMBankTransaction

    monkeypatch.setattr(routes, "models", lambda: {})
    first_headers = register_and_login(client, "first@example.com")
    second_headers = register_and_login(client, "second@example.com")
    other_account = client.get("/api/bank/accounts", headers=second_headers).json[0]
    response = client.post("/api/bank/transactions", headers=first_headers, json={
        "account_id": other_account["id"],
        "amount": "10.00",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "distance_from_last_km": 1,
        "idempotency_key": "test-id-check-1",
    })
    assert response.status_code == 404
    with client.application.app_context():
        assert MGMBankTransaction.query.count() == 0


def test_xgboost_prediction_returns_feature_contributions():
    import numpy as np
    import pandas as pd
    from xgboost import XGBClassifier

    from app.ml import FEATURES, predict

    training_data = pd.DataFrame(
        [
            [10, 12, 0, 10, 1],
            [20, 13, 1, 15, 2],
            [900, 2, 8, 20, 500],
            [1200, 3, 10, 30, 800],
        ],
        columns=FEATURES,
    )
    model = XGBClassifier(
        n_estimators=5, max_depth=2, n_jobs=1, eval_metric="logloss"
    )
    model.fit(training_data, np.array([0, 0, 1, 1]))

    result = predict(
        {"xgboost": model},
        dict(zip(FEATURES, training_data.iloc[0].tolist())),
        "xgboost",
    )

    assert result["classification"] in {"fraud", "genuine"}
    assert len(result["explanation"]) == 3
