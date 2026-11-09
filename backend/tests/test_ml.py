import numpy as np
import pandas as pd

from app import ml
from app.train import chronological_partitions, demo_frame, select_threshold, train


def test_demo_dataset_has_both_classes_and_new_account_profiles():
    frame = demo_frame(rows=10_000)

    assert frame["is_fraud"].nunique() == 2
    assert 0.05 < frame["is_fraud"].mean() < 0.15
    assert (frame["avg_amount_30d"] == 0).any()
    large = frame["amount"] >= 2500
    velocity = (
        (frame["transactions_last_24h"] >= 5)
        & (frame["amount"] >= np.maximum(frame["avg_amount_30d"] * 2, 100))
    )
    travel = (
        (frame["distance_from_last_km"] >= 100)
        & (frame["transaction_hour"] <= 5)
        & (frame["amount"] >= 250)
    )
    spike = (
        (frame["avg_amount_30d"] > 0)
        & (frame["amount"] >= np.maximum(frame["avg_amount_30d"] * 4, 500))
    )
    assert large.sum() >= 200
    assert velocity.sum() >= 200
    assert travel.sum() >= 200
    assert spike.sum() >= 200
    assert frame.loc[large | velocity | travel | spike, "is_fraud"].eq(1).all()


def test_validation_threshold_maximizes_f1_for_imbalanced_predictions():
    threshold = select_threshold(
        [0, 0, 1, 1],
        [0.1, 0.4, 0.35, 0.8],
    )

    assert threshold == 0.35


def test_chronological_split_keeps_duplicate_timestamps_together():
    timestamps = pd.Series(
        pd.to_datetime(
            ["2026-01-01"] * 4
            + ["2026-01-02"] * 4
            + ["2026-01-03"] * 4
            + ["2026-01-04"] * 4
            + ["2026-01-05"] * 4,
            utc=True,
        )
    )

    training, validation, testing = chronological_partitions(timestamps)

    assert not (training & validation).any()
    assert not (training & testing).any()
    assert not (validation & testing).any()
    assert timestamps[training].max() < timestamps[validation].min()
    assert timestamps[validation].max() < timestamps[testing].min()


def test_prediction_uses_threshold_saved_with_model(monkeypatch):
    class Model:
        fraud_threshold_ = 0.2

        def predict_proba(self, _frame):
            return np.array([[0.75, 0.25]])

    class Explainer:
        def shap_values(self, _frame):
            return np.zeros((1, len(ml.FEATURES), 2))

    monkeypatch.setattr(ml.shap, "TreeExplainer", lambda _model: Explainer())
    ml._explainers.clear()
    result = ml.predict(
        {"random_forest": Model()},
        {
            "amount": 100,
            "transaction_hour": 12,
            "transactions_last_24h": 0,
            "avg_amount_30d": 50,
            "distance_from_last_km": 2,
        },
        "random_forest",
    )

    assert result["threshold"] == 0.2
    assert result["classification"] == "fraud"


def test_training_persists_all_models_with_independent_test_metrics(
    monkeypatch, tmp_path
):
    import app.train as training

    monkeypatch.setattr(training, "MODEL_DIR", tmp_path)
    frame = demo_frame(rows=3_000)
    metrics = train(frame)

    assert {row["model_name"] for row in metrics} == set(ml.MODEL_NAMES)
    for result in metrics:
        model_name = result["model_name"]
        model = ml.joblib.load(tmp_path / f"{model_name}.joblib")
        model_metrics = result["metrics"]
        assert hasattr(model, "fraud_threshold_")
        assert 0 < model_metrics["threshold"] < 1
        assert model_metrics["validation_rows"] == 480
        assert model_metrics["test_rows"] == 600
        assert 0 <= model_metrics["precision"] <= 1
        assert 0 <= model_metrics["recall"] <= 1
        assert 0 <= model_metrics["f1"] <= 1


def test_logistic_regression_prediction_and_feature_contributions(
    monkeypatch, tmp_path
):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(random_state=7),
    )
    training = demo_frame(rows=3_000)
    model.fit(training[ml.FEATURES], training["is_fraud"])
    model.fraud_threshold_ = 0.4
    monkeypatch.setattr(ml, "MODEL_DIR", tmp_path)
    ml.joblib.dump(model, tmp_path / "logistic_regression.joblib")
    loaded = ml.load_models()
    result = ml.predict(
        loaded,
        {
            "amount": 5000,
            "transaction_hour": 2,
            "transactions_last_24h": 8,
            "avg_amount_30d": 100,
            "distance_from_last_km": 150,
        },
        "logistic_regression",
    )

    assert result["classification"] == "fraud"
    assert result["threshold"] == 0.4
    assert len(result["explanation"]) == 3
    assert any(item["impact"] > 0 for item in result["explanation"])
