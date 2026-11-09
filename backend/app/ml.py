import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

MODEL_NAMES = ("random_forest", "xgboost", "logistic_regression")
FEATURES = [
    "amount",
    "transaction_hour",
    "transactions_last_24h",
    "avg_amount_30d",
    "distance_from_last_km",
]
MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "untrained")
THRESHOLD = float(os.getenv("FRAUD_THRESHOLD", "0.5"))
if not 0 <= THRESHOLD <= 1:
    raise ValueError("FRAUD_THRESHOLD must be between 0 and 1")
_explainers = {}


def load_models():
    models = {}
    for name in MODEL_NAMES:
        path = MODEL_DIR / f"{name}.joblib"
        if path.exists():
            models[name] = joblib.load(path)
    return models


def predict(models, features, model_name="xgboost"):
    if model_name not in models:
        raise FileNotFoundError(
            f"The {model_name} model is not trained. Train models using the documented command."
        )
    frame = pd.DataFrame([features], columns=FEATURES)
    model = models[model_name]
    probability = float(model.predict_proba(frame)[0, 1])
    if model_name == "xgboost":
        contributions = model.get_booster().predict(
            xgb.DMatrix(frame), pred_contribs=True
        )
        values = np.asarray(contributions)[0, :-1]
    elif model_name == "logistic_regression":
        scaler = model.named_steps["standardscaler"]
        classifier = model.named_steps["logisticregression"]
        values = classifier.coef_[0] * scaler.transform(frame)[0]
    else:
        if model_name not in _explainers:
            _explainers[model_name] = shap.TreeExplainer(model)
        shap_values = _explainers[model_name].shap_values(frame)
        if isinstance(shap_values, list):
            values = np.asarray(shap_values[-1])[0]
        else:
            values = np.asarray(shap_values)
            if values.ndim == 3:
                values = values[0, :, 1]
            elif values.ndim == 2:
                values = values[0]
    explanation = [
        {"feature": feature, "value": float(features[feature]), "impact": round(float(impact), 6)}
        for feature, impact in sorted(
            zip(FEATURES, values), key=lambda item: abs(item[1]), reverse=True
        )[:3]
    ]
    return {
        "model_name": model_name,
        "model_version": MODEL_VERSION,
        "fraud_probability": probability,
        "risk_score": round(probability * 100),
        "classification": (
            "fraud"
            if probability >= float(getattr(model, "fraud_threshold_", THRESHOLD))
            else "genuine"
        ),
        "threshold": float(getattr(model, "fraud_threshold_", THRESHOLD)),
        "explanation": explanation,
    }


def evaluation_history():
    path = MODEL_DIR / "metrics.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return json.load(file)
