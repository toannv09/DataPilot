"""Detect loại bài toán ML và chọn model baseline phù hợp."""

import json

import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from xgboost import XGBClassifier, XGBRegressor

MODEL_REGISTRY = {
    "regression": {
        "LinearRegression": LinearRegression,
        "RandomForestRegressor": lambda **kw: RandomForestRegressor(random_state=42, **kw),
        "XGBRegressor": lambda **kw: XGBRegressor(random_state=42, **kw),
    },
    "classification": {
        "LogisticRegression": lambda **kw: LogisticRegression(max_iter=1000, class_weight="balanced", **kw),
        "RandomForestClassifier": lambda **kw: RandomForestClassifier(
            random_state=42, class_weight="balanced", **kw
        ),
        "XGBClassifier": lambda **kw: XGBClassifier(random_state=42, eval_metric="logloss", **kw),
    },
    "clustering": {
        "KMeans": lambda **kw: KMeans(random_state=42, n_init=10, **{"n_clusters": 3, **kw}),
        "DBSCAN": lambda **kw: DBSCAN(**kw),
    },
}

# Param distributions cho RandomizedSearchCV. Model không có trong dict này coi như không tune.
PARAM_DISTRIBUTIONS = {
    "RandomForestRegressor": {
        "n_estimators": [50, 100, 200, 300],
        "max_depth": [None, 5, 10, 20],
        "min_samples_split": [2, 5, 10],
    },
    "RandomForestClassifier": {
        "n_estimators": [50, 100, 200, 300],
        "max_depth": [None, 5, 10, 20],
        "min_samples_split": [2, 5, 10],
    },
    "XGBRegressor": {
        "n_estimators": [50, 100, 200],
        "max_depth": [3, 5, 7],
        "learning_rate": [0.01, 0.05, 0.1, 0.2],
    },
    "XGBClassifier": {
        "n_estimators": [50, 100, 200],
        "max_depth": [3, 5, 7],
        "learning_rate": [0.01, 0.05, 0.1, 0.2],
    },
    "LogisticRegression": {
        "C": [0.01, 0.1, 1, 10, 100],
    },
}

# Grid vét cạn cho clustering (không dùng RandomizedSearchCV vì unsupervised).
CLUSTERING_SEARCH_GRID = {
    "KMeans": {"n_clusters": [2, 3, 4, 5, 6]},
    "DBSCAN": {"eps": [0.3, 0.5, 0.8, 1.0, 1.5], "min_samples": [3, 5, 10]},
}


def detect_task_type(df, target_col):
    """Trả về 'regression' / 'classification' / 'clustering'."""
    if target_col is None or target_col not in df.columns:
        return "clustering"

    series = df[target_col].dropna()
    if pd.api.types.is_numeric_dtype(series):
        # nunique() thấp không đủ để coi là classification — cột liên tục (vd điểm đánh giá
        # 1.2/3.6/4.8) tình cờ có ít giá trị duy nhất trong sample vẫn là continuous, fit
        # classifier lên nó sẽ raise "Unknown label type: continuous" ở sklearn.
        is_integer_like = (series == series.round()).all()
        if is_integer_like and series.nunique() <= 10:
            return "classification"
        return "regression"

    return "classification"


def get_baseline_models(task_type, selected_model=None, model_params=None):
    """Trả về list[(tên, model)].

    selected_model=None -> toàn bộ baseline của task_type.
    selected_model cụ thể -> chỉ model đó, khởi tạo với model_params (nếu có).
    """
    registry = MODEL_REGISTRY.get(task_type)
    if registry is None:
        raise ValueError(f"task_type không hợp lệ: {task_type}")

    if selected_model is None:
        return [(name, ctor()) for name, ctor in registry.items()]

    ctor = registry.get(selected_model)
    if ctor is None:
        raise ValueError(f"model '{selected_model}' không hợp lệ cho task_type '{task_type}'")

    return [(selected_model, ctor(**(model_params or {})))]


def get_param_distribution(model_name):
    """Trả về param distribution cho RandomizedSearchCV, hoặc None nếu model không tune."""
    return PARAM_DISTRIBUTIONS.get(model_name)


def suggest_models_by_llm(task_desc, eda_insights):
    """LLM gợi ý 2-3 model phù hợp theo context domain."""
    from llm.client import call_llm
    from llm.prompts.ml_prompt import TASK_DETECTION_USER

    prompt = TASK_DETECTION_USER.format(
        user_query=task_desc, dataset_info="", eda_insights=eda_insights
    )
    response = call_llm(prompt)

    try:
        data = json.loads(response)
        return data.get("suggested_models", [])
    except (json.JSONDecodeError, TypeError):
        return []
