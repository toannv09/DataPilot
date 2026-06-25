"""Train, cross-validate, so sánh và lưu model."""

import os

import joblib
import numpy as np
import pandas as pd
from sklearn.base import ClusterMixin, is_regressor
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    silhouette_score,
)
from sklearn.model_selection import RandomizedSearchCV, cross_val_score

from tools.ml.model_selector import CLUSTERING_SEARCH_GRID, get_param_distribution

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "models")

HIGHER_IS_BETTER_METRICS = {"r2", "accuracy", "f1", "precision", "recall", "silhouette"}

RANDOM_SEARCH_N_ITER = 8
RANDOM_SEARCH_CV = 3


def _optimize_supervised(name, model, X_train, y_train):
    """RandomizedSearchCV nếu model có param distribution, ngược lại trả model gốc."""
    distribution = get_param_distribution(name)
    if not distribution:
        model.fit(X_train, y_train)
        return model

    scoring = "r2" if is_regressor(model) else "f1_weighted"
    n_iter = min(RANDOM_SEARCH_N_ITER, int(np.prod([len(v) for v in distribution.values()])))
    search = RandomizedSearchCV(
        model, distribution, n_iter=n_iter, cv=RANDOM_SEARCH_CV, scoring=scoring, random_state=42
    )
    search.fit(X_train, y_train)
    return search.best_estimator_


def _optimize_clustering(name, model, X_train):
    """Vét cạn nhỏ tham số clustering, chọn theo silhouette cao nhất."""
    grid = CLUSTERING_SEARCH_GRID.get(name)
    if not grid:
        return model

    from sklearn.cluster import DBSCAN, KMeans

    best_model, best_score = model, -1.0
    keys = list(grid.keys())

    def combos(idx, current):
        if idx == len(keys):
            yield dict(current)
            return
        key = keys[idx]
        for value in grid[key]:
            current[key] = value
            yield from combos(idx + 1, current)
            del current[key]

    for params in combos(0, {}):
        if name == "KMeans":
            candidate = KMeans(random_state=42, n_init=10, **params)
        elif name == "DBSCAN":
            candidate = DBSCAN(**params)
        else:
            continue

        candidate.fit(X_train)
        labels = candidate.labels_
        if len(set(labels)) <= 1:
            continue

        score = silhouette_score(X_train, labels)
        if score > best_score:
            best_score, best_model = score, candidate

    return best_model


def train_and_evaluate(X_train, y_train, X_test, y_test, models, optimize=False):
    """Train tất cả model trong `models` (list[(tên, model)]), trả dict kết quả + metrics."""
    results = {}

    for name, model in models:
        if isinstance(model, ClusterMixin):
            if optimize:
                model = _optimize_clustering(name, model, X_train)
            else:
                model.fit(X_train)

            labels = model.labels_ if hasattr(model, "labels_") else model.predict(X_train)

            metrics = {}
            if len(set(labels)) > 1:
                metrics["silhouette"] = float(silhouette_score(X_train, labels))
            if hasattr(model, "inertia_"):
                metrics["inertia"] = float(model.inertia_)

            results[name] = {"model": model, "metrics": metrics, "y_pred": labels}

        elif is_regressor(model):
            if optimize:
                model = _optimize_supervised(name, model, X_train, y_train)
            else:
                model.fit(X_train, y_train)

            y_pred = model.predict(X_test)
            metrics = {
                "rmse": float(mean_squared_error(y_test, y_pred) ** 0.5),
                "mae": float(mean_absolute_error(y_test, y_pred)),
                "r2": float(r2_score(y_test, y_pred)),
            }
            results[name] = {"model": model, "metrics": metrics, "y_pred": y_pred}

        else:
            # XGBClassifier không nhận class_weight — set scale_pos_weight động theo tỉ lệ class
            # (chỉ áp dụng nhị phân; bỏ qua nếu đa lớp hoặc đã set sẵn).
            if type(model).__name__ == "XGBClassifier" and y_train.nunique() == 2:
                counts = y_train.value_counts()
                model.set_params(scale_pos_weight=float(counts.max() / counts.min()))

            if optimize:
                model = _optimize_supervised(name, model, X_train, y_train)
            else:
                model.fit(X_train, y_train)

            y_pred = model.predict(X_test)
            metrics = {
                "accuracy": float(accuracy_score(y_test, y_pred)),
                "f1": float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
                "precision": float(precision_score(y_test, y_pred, average="weighted", zero_division=0)),
                "recall": float(recall_score(y_test, y_pred, average="weighted", zero_division=0)),
            }
            results[name] = {"model": model, "metrics": metrics, "y_pred": y_pred}

    return results


def cross_validate_model(model, X, y, cv=5):
    """Cross-validate, trả mean ± std của metric phù hợp với loại model."""
    scoring = "r2" if is_regressor(model) else "accuracy"
    scores = cross_val_score(model, X, y, cv=cv, scoring=scoring)
    return {"scoring": scoring, "mean": float(scores.mean()), "std": float(scores.std())}


def compare_models(results):
    """Bảng leaderboard so sánh các model từ kết quả train_and_evaluate."""
    rows = []
    for name, r in results.items():
        row = {"model": name}
        row.update(r["metrics"])
        rows.append(row)
    return pd.DataFrame(rows)


def get_best_model(results, metric):
    """Trả về model tốt nhất theo `metric`."""
    higher_is_better = metric in HIGHER_IS_BETTER_METRICS

    best_name, best_value = None, None
    for name, r in results.items():
        value = r["metrics"].get(metric)
        if value is None:
            continue
        if best_value is None or (value > best_value if higher_is_better else value < best_value):
            best_value = value
            best_name = name

    return results[best_name]["model"] if best_name else None


def save_model(model, name, pipeline=None, task_type=None, target_col=None, feature_names=None,
                metric=None, metrics=None):
    """Lưu bundle {model, pipeline, task_type, target_col, feature_names, metric, metrics} vào outputs/models/."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, f"{name}.pkl")
    bundle = {
        "model": model,
        "pipeline": pipeline,
        "task_type": task_type,
        "target_col": target_col,
        "feature_names": feature_names,
        "metric": metric,
        "metrics": metrics,
    }
    joblib.dump(bundle, path)
    return path


def load_model_bundle(path):
    """Load model đã lưu. Trả về bundle dict; nếu file là raw model (.pkl cũ/user upload), bọc lại thành bundle."""
    obj = joblib.load(path)

    if isinstance(obj, dict) and "model" in obj:
        return obj

    return {
        "model": obj,
        "pipeline": None,
        "task_type": None,
        "target_col": None,
        "feature_names": getattr(obj, "feature_names_in_", None),
        "metric": None,
        "metrics": None,
    }
