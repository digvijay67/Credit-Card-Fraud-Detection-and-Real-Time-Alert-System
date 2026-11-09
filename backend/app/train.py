import argparse
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from app.ml import FEATURES, MODEL_DIR, MODEL_VERSION, THRESHOLD


def demo_frame(rows=10000, seed=7):
    rng = np.random.default_rng(seed)
    amount = rng.lognormal(mean=3.5, sigma=1.2, size=rows).clip(1, 100000)
    hour = rng.integers(0, 24, size=rows)
    recent = rng.poisson(1.3, size=rows)
    average = rng.lognormal(mean=3.4, sigma=0.8, size=rows).clip(1, 30000)
    average[rng.random(rows) < 0.08] = 0
    distance = rng.exponential(scale=35, size=rows).clip(0, 2000)
    if rows >= 4:
        scenario_size = min(max(1, rows // 50), rows // 4)
        scenario_indices = rng.permutation(rows)
        large_indices = scenario_indices[:scenario_size]
        velocity_indices = scenario_indices[scenario_size : 2 * scenario_size]
        travel_indices = scenario_indices[2 * scenario_size : 3 * scenario_size]
        spike_indices = scenario_indices[3 * scenario_size : 4 * scenario_size]
        amount[large_indices] = rng.uniform(2500, 10000, scenario_size)
        average[velocity_indices] = rng.uniform(50, 200, scenario_size)
        recent[velocity_indices] = rng.integers(6, 13, scenario_size)
        amount[velocity_indices] = np.maximum(
            average[velocity_indices] * 2.5, 120
        )
        distance[travel_indices] = rng.uniform(120, 1500, scenario_size)
        hour[travel_indices] = rng.integers(0, 6, scenario_size)
        amount[travel_indices] = np.maximum(amount[travel_indices], 300)
        average[spike_indices] = rng.uniform(50, 2000, scenario_size)
        amount[spike_indices] = np.maximum(
            average[spike_indices] * 5, 600
        )
    spending_spike = (average > 0) & (amount >= np.maximum(average * 4, 500))
    high_velocity = (recent >= 5) & (amount >= np.maximum(average * 2, 100))
    unusual_travel = (distance >= 100) & (hour <= 5) & (amount >= 250)
    unusually_large = amount >= 2500
    fraud = (
        spending_spike | high_velocity | unusual_travel | unusually_large
    ).astype(int)
    return pd.DataFrame({
        "amount": amount,
        "transaction_hour": hour,
        "transactions_last_24h": recent,
        "avg_amount_30d": average,
        "distance_from_last_km": distance,
        "is_fraud": fraud,
    })


def select_threshold(labels, probabilities):
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    if not thresholds.size:
        return THRESHOLD
    f1_scores = (
        2 * precision[:-1] * recall[:-1]
        / np.maximum(precision[:-1] + recall[:-1], np.finfo(float).eps)
    )
    best_index = max(
        range(len(thresholds)),
        key=lambda index: (
            f1_scores[index],
            precision[index],
            thresholds[index],
        ),
    )
    return float(thresholds[best_index])


def chronological_partitions(timestamps):
    unique_timestamps = timestamps.drop_duplicates().sort_values()
    train_end = int(len(unique_timestamps) * 0.6)
    validation_end = int(len(unique_timestamps) * 0.8)
    if (
        train_end < 1
        or validation_end <= train_end
        or validation_end >= len(unique_timestamps)
    ):
        raise ValueError(
            "Timestamp data must contain at least three chronological partitions"
        )
    train_cutoff = unique_timestamps.iloc[train_end]
    validation_cutoff = unique_timestamps.iloc[validation_end]
    return (
        timestamps < train_cutoff,
        (timestamps >= train_cutoff) & (timestamps < validation_cutoff),
        timestamps >= validation_cutoff,
    )


def train(frame):
    required = set(FEATURES + ["is_fraud"])
    if not required.issubset(frame.columns):
        raise ValueError(f"Dataset must contain columns: {', '.join(sorted(required))}")
    timestamps = (
        pd.to_datetime(frame["occurred_at"], utc=True, errors="coerce")
        if "occurred_at" in frame.columns
        else None
    )
    frame = frame[FEATURES + ["is_fraud"]].apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    if timestamps is not None:
        valid = timestamps.notna() & frame.notna().all(axis=1)
        frame = frame.loc[valid]
        timestamps = timestamps.loc[valid]
    else:
        frame = frame.dropna()
    if frame.empty:
        raise ValueError("Dataset has no complete, finite training rows")
    if not set(frame["is_fraud"].unique()).issubset({0, 1}) or frame["is_fraud"].nunique() != 2:
        raise ValueError("is_fraud must contain both binary labels 0 and 1")
    labels = frame["is_fraud"].astype(int)
    if timestamps is None:
        x_development, x_test, y_development, y_test = train_test_split(
            frame[FEATURES], labels,
            test_size=0.2, random_state=42, stratify=labels,
        )
        x_train, x_validation, y_train, y_validation = train_test_split(
            x_development, y_development,
            test_size=0.2, random_state=43, stratify=y_development,
        )
    else:
        train_mask, validation_mask, test_mask = chronological_partitions(timestamps)
        x_train = frame.loc[train_mask, FEATURES]
        y_train = labels.loc[train_mask]
        x_validation = frame.loc[validation_mask, FEATURES]
        y_validation = labels.loc[validation_mask]
        x_test = frame.loc[test_mask, FEATURES]
        y_test = labels.loc[test_mask]
    if any(part.nunique() != 2 for part in (y_train, y_validation, y_test)):
        raise ValueError(
            "Training, validation, and test partitions must contain both fraud classes; "
            "check the dataset size, class distribution, and timestamp range"
        )
    negatives = int((y_train == 0).sum())
    positives = int((y_train == 1).sum())
    estimators = {
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=2, class_weight="balanced",
            random_state=42, n_jobs=-1,
        ),
        "xgboost": XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            scale_pos_weight=negatives / max(positives, 1),
            eval_metric="logloss", random_state=42, n_jobs=-1,
        ),
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=42,
            ),
        ),
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for name, model in estimators.items():
        model.fit(x_train, y_train)
        validation_probability = model.predict_proba(x_validation)[:, 1]
        threshold = select_threshold(y_validation, validation_probability)
        model.fraud_threshold_ = threshold
        probability = model.predict_proba(x_test)[:, 1]
        predicted = probability >= threshold
        tn, fp, fn, tp = confusion_matrix(y_test, predicted, labels=[0, 1]).ravel()
        metrics = {
            "accuracy": float(accuracy_score(y_test, predicted)),
            "precision": float(precision_score(y_test, predicted, zero_division=0)),
            "recall": float(recall_score(y_test, predicted, zero_division=0)),
            "f1": float(f1_score(y_test, predicted, zero_division=0)),
            "pr_auc": float(average_precision_score(y_test, probability)),
            "threshold": threshold,
            "confusion_matrix": {"true_negative": int(tn), "false_positive": int(fp),
                                 "false_negative": int(fn), "true_positive": int(tp)},
            "test_rows": int(len(y_test)),
            "validation_rows": int(len(y_validation)),
            "fraud_rate": float(y_test.mean()),
        }
        joblib.dump(model, MODEL_DIR / f"{name}.joblib")
        results.append({
            "model_name": name,
            "model_version": MODEL_VERSION,
            "metrics": metrics,
        })
    with (MODEL_DIR / "metrics.json").open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)
    return results


def main():
    parser = argparse.ArgumentParser(description="Train fraud models from a labeled CSV dataset.")
    parser.add_argument("--csv", help="Path to a labeled CSV with the required model columns")
    parser.add_argument(
        "--demo-data", action="store_true",
        help="Train on generated synthetic data for UI/API demonstration only",
    )
    args = parser.parse_args()
    if bool(args.csv) == args.demo_data:
        parser.error("Provide exactly one of --csv PATH or --demo-data")
    frame = demo_frame() if args.demo_data else pd.read_csv(args.csv)
    results = train(frame)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
