"""Biểu đồ đánh giá ML. Tất cả hàm save PNG vào outputs/ml_charts/, trả về path."""

import matplotlib
matplotlib.use("Agg")

import os
import uuid

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from sklearn.metrics import confusion_matrix

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "ml_charts")


def _save(fig, name):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{name}_{uuid.uuid4().hex[:8]}.png")
    fig.savefig(path, bbox_inches="tight", dpi=100)
    plt.close(fig)
    return path


def plot_confusion_matrix(y_true, y_pred, labels=None):
    """Confusion matrix."""
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    # seaborn heatmap không nhận xticklabels=None — cần "auto" để tự suy ra nhãn.
    tick_labels = labels if labels is not None else "auto"

    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=tick_labels, yticklabels=tick_labels, ax=ax)
    ax.set_xlabel("Dự đoán")
    ax.set_ylabel("Thực tế")
    ax.set_title("Confusion Matrix")
    return _save(fig, "confusion_matrix")


def plot_feature_importance(model, feature_names):
    """Feature importance bar chart."""
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        importances = np.abs(np.ravel(model.coef_))
    else:
        raise ValueError("Model không hỗ trợ feature importance")

    order = np.argsort(importances)[::-1]
    sorted_features = [feature_names[i] for i in order]
    sorted_importances = importances[order]

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.barplot(x=sorted_importances, y=sorted_features, ax=ax)
    ax.set_title("Feature Importance")
    ax.set_xlabel("Importance")
    return _save(fig, "feature_importance")


def plot_actual_vs_predicted(y_true, y_pred):
    """Scatter plot actual vs predicted."""
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_true, y_pred, alpha=0.5)

    lims = [min(min(y_true), min(y_pred)), max(max(y_true), max(y_pred))]
    ax.plot(lims, lims, "r--")

    ax.set_xlabel("Thực tế")
    ax.set_ylabel("Dự đoán")
    ax.set_title("Actual vs Predicted")
    return _save(fig, "actual_vs_predicted")


def plot_residuals(y_true, y_pred):
    """Residual plot."""
    residuals = np.array(y_true) - np.array(y_pred)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(y_pred, residuals, alpha=0.5)
    ax.axhline(0, color="r", linestyle="--")
    ax.set_xlabel("Dự đoán")
    ax.set_ylabel("Residual")
    ax.set_title("Residual Plot")
    return _save(fig, "residuals")


def plot_cluster_scatter(X, labels):
    """Scatter 2D các cluster (PCA nếu >2 chiều)."""
    X = np.asarray(X)
    if X.shape[1] > 2:
        from sklearn.decomposition import PCA
        X = PCA(n_components=2, random_state=42).fit_transform(X)

    fig, ax = plt.subplots(figsize=(7, 6))
    scatter = ax.scatter(X[:, 0], X[:, 1], c=labels, cmap="tab10", alpha=0.7)
    ax.set_xlabel("Thành phần 1")
    ax.set_ylabel("Thành phần 2")
    ax.set_title("Phân nhóm (Clustering)")
    legend = ax.legend(*scatter.legend_elements(), title="Cluster")
    ax.add_artist(legend)
    return _save(fig, "cluster_scatter")


def plot_model_comparison(leaderboard, metric=None):
    """Bar chart so sánh các model theo `metric` (mặc định: metric đầu tiên trong leaderboard)."""
    metric_cols = [c for c in leaderboard.columns if c != "model"]
    if metric not in metric_cols:
        metric = metric_cols[0]

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=leaderboard, x="model", y=metric, ax=ax)
    ax.set_title(f"So sánh model theo {metric}")
    ax.tick_params(axis="x", rotation=30)
    return _save(fig, "model_comparison")
