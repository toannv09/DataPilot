"""Sinh lại code Python từ log/config THỰC TẾ đã chạy — dùng cho nút 'Xem/tải code' ở UI.

Không dùng LLM viết lại — code sinh ra map trực tiếp 1:1 với tool/config đã thực thi
(lấy từ result.log / result.data["config"]), đảm bảo đúng với cái đã chạy, không suy diễn.
"""


def _resolve_tool_func(tool_name):
    from agents.eda_agent import TOOL_REGISTRY

    return TOOL_REGISTRY.get(tool_name)


def _format_call(tool_name, params):
    args = ", ".join(f"{k}={v!r}" for k, v in (params or {}).items())
    return f"{tool_name}(df{', ' + args if args else ''})"


# Nhóm tool theo nhóm trong planner_prompt.py — chỉ để chia comment cho code dễ đọc,
# không ảnh hưởng logic chạy thật.
_TOOL_CATEGORY = {
    "check_missing": "Kiểm tra chất lượng dữ liệu",
    "check_duplicates": "Kiểm tra chất lượng dữ liệu",
    "check_type_mismatch": "Kiểm tra chất lượng dữ liệu",
    "check_outliers_iqr": "Kiểm tra chất lượng dữ liệu",
    "check_outliers_rolling": "Kiểm tra chất lượng dữ liệu",
    "basic_stats": "Thống kê mô tả",
    "skewness_kurtosis": "Thống kê mô tả",
    "normality_test": "Thống kê mô tả",
    "group_stats": "Thống kê mô tả",
    "correlation_matrix": "Phân tích tương quan",
    "spearman_correlation": "Phân tích tương quan",
    "lag_correlation": "Phân tích tương quan",
    "mutual_info_scores": "Phân tích tương quan",
    "time_series_decompose": "Phân tích theo thời gian",
    "hourly_pattern": "Phân tích theo thời gian",
    "weekly_pattern": "Phân tích theo thời gian",
    "monthly_pattern": "Phân tích theo thời gian",
    "plot_distribution": "Trực quan hóa",
    "plot_violin": "Trực quan hóa",
    "plot_boxplot": "Trực quan hóa",
    "plot_boxplot_by": "Trực quan hóa",
    "plot_scatter": "Trực quan hóa",
    "plot_heatmap": "Trực quan hóa",
    "plot_pairplot": "Trực quan hóa",
    "plot_time_series": "Trực quan hóa",
    "plot_seasonal_pattern": "Trực quan hóa",
    "plot_missing_heatmap": "Trực quan hóa",
    "plot_decomposition": "Trực quan hóa",
    "plot_mi_scores": "Trực quan hóa",
}


def eda_log_to_code(log):
    """Sinh code Python từ log thực thi EDA — chỉ lấy step status='success' (bỏ skipped/error).

    Chèn comment theo nhóm (kiểm tra chất lượng / thống kê / tương quan / time series /
    trực quan hóa) để dễ đọc — comment chỉ mang tính phân nhóm, không phải mô tả từng bước.
    """
    used_tools = []
    call_lines = []
    prev_category = None
    for entry in log or []:
        if entry.get("status") != "success":
            continue
        tool_name = entry.get("step")
        func = _resolve_tool_func(tool_name)
        if func is None:
            continue
        if tool_name not in used_tools:
            used_tools.append(tool_name)

        category = _TOOL_CATEGORY.get(tool_name)
        if category and category != prev_category:
            if call_lines:
                call_lines.append("")
            call_lines.append(f"# {category}")
            prev_category = category

        call_lines.append(_format_call(tool_name, entry.get("params", {})))

    imports_by_module = {}
    for tool_name in used_tools:
        func = _resolve_tool_func(tool_name)
        imports_by_module.setdefault(func.__module__, set()).add(func.__name__)
    import_lines = [
        f"from {module} import {', '.join(sorted(names))}"
        for module, names in sorted(imports_by_module.items())
    ]

    if not call_lines:
        return None

    header = [
        "import pandas as pd",
        *import_lines,
        "",
        'df = pd.read_csv("your_file.csv")  # thay bằng file dữ liệu của bạn',
        "",
    ]
    return "\n".join(header + call_lines) + "\n"


def preprocessing_config_to_code(cfg, target_col=None, steps=None):
    """Sinh code Python từ config thực tế PreprocessingAgent đã dùng cho PreprocessingPipeline.

    steps: list[str] — mô tả tiếng Việt từng việc đã làm (PreprocessingAgent.steps_log), chèn
    thành comment phía trên lệnh fit_transform để dễ hiểu — vẫn chỉ 1 lệnh thật, không bịa thêm.
    """
    if not cfg:
        return None

    args = []
    if target_col:
        args.append(f"target_col={target_col!r}")
    for key in ("fill_method", "skip_outlier", "outlier_method", "skip_encode", "skip_scale", "scale_method"):
        if key in cfg:
            args.append(f"{key}={cfg[key]!r}")
    args_block = ",\n    ".join(args)

    comment_block = ""
    if steps:
        comment_lines = "\n".join(f"# - {s}" for s in steps)
        comment_block = f"# Các bước đã thực hiện:\n{comment_lines}\n\n"

    return (
        "from tools.ml.pipeline import PreprocessingPipeline\n\n"
        f"{comment_block}"
        "pipeline = PreprocessingPipeline()\n"
        "df_processed = pipeline.fit_transform(\n"
        "    df,\n"
        f"    {args_block},\n"
        ")\n"
    )


# Import path cố định cho từng model trong MODEL_REGISTRY (tools/ml/model_selector.py).
_MODEL_IMPORTS = {
    "LinearRegression": ("sklearn.linear_model", "LinearRegression"),
    "LogisticRegression": ("sklearn.linear_model", "LogisticRegression"),
    "RandomForestRegressor": ("sklearn.ensemble", "RandomForestRegressor"),
    "RandomForestClassifier": ("sklearn.ensemble", "RandomForestClassifier"),
    "XGBRegressor": ("xgboost", "XGBRegressor"),
    "XGBClassifier": ("xgboost", "XGBClassifier"),
    "KMeans": ("sklearn.cluster", "KMeans"),
    "DBSCAN": ("sklearn.cluster", "DBSCAN"),
}


def training_log_to_code(result_data, log, target_col=None):
    """Sinh code Python từ log thực thi Training — mỗi model dùng đúng hyperparameter thật
    (lấy từ model.get_params() đã lưu trong log, không phải giá trị mặc định/suy diễn).
    """
    model_entries = [e for e in (log or []) if e.get("status") == "success" and "params" in e]
    if not model_entries:
        return None

    task_type = (result_data or {}).get("task_type")
    split_method = (result_data or {}).get("split_method")
    split_ratio = (result_data or {}).get("split_ratio", 0.8)
    used_existing_pipeline = (result_data or {}).get("used_existing_pipeline", False)

    imports_by_module = {}
    for e in model_entries:
        info = _MODEL_IMPORTS.get(e["step"])
        if info:
            imports_by_module.setdefault(info[0], set()).add(info[1])
    import_lines = [
        f"from {module} import {', '.join(sorted(names))}"
        for module, names in sorted(imports_by_module.items())
    ]

    lines = ["import pandas as pd", *import_lines]
    if split_method == "clustering" and not used_existing_pipeline:
        lines.append("from tools.ml.preprocessor import NumericScaler, handle_missing")
    elif split_method == "time":
        lines.append("from tools.ml.preprocessor import handle_missing, train_test_split_time")
    else:
        lines.append("from tools.ml.preprocessor import handle_missing, train_test_split_random")
    lines.append("from tools.ml.trainer import compare_models, train_and_evaluate")

    lines += [
        "",
        'df = pd.read_csv("your_file.csv")  # thay bằng file dữ liệu của bạn',
        'df_numeric = df.select_dtypes(include="number").copy()',
        "",
        "# Điền giá trị thiếu (median) cho cột số còn NaN trước khi train",
        "for col in df_numeric.columns:",
        "    if df_numeric[col].isna().any():",
        '        df_numeric = handle_missing(df_numeric, col, "median")',
        "",
    ]

    if split_method == "clustering":
        if used_existing_pipeline:
            lines.append("# Dữ liệu đã qua Preprocessing stage (Full Pipeline) -> đã được scale từ trước")
            lines.append("X_train, y_train, X_test, y_test = df_numeric, None, df_numeric, None")
        else:
            lines.append("# KMeans/DBSCAN dựa trên khoảng cách -> bắt buộc scale trước")
            lines.append("scaler = NumericScaler()")
            lines.append("df_scaled = scaler.fit_transform(df_numeric)")
            lines.append("X_train, y_train, X_test, y_test = df_scaled, None, df_scaled, None")
    elif split_method == "time":
        lines.append(f"X_train, X_test, y_train, y_test = train_test_split_time(df_numeric, {target_col!r}, {split_ratio})")
    else:
        lines.append(f"X_train, X_test, y_train, y_test = train_test_split_random(df_numeric, {target_col!r}, {split_ratio})")

    lines.append("")
    lines.append("models = [")
    for e in model_entries:
        name = e["step"]
        params = e.get("params", {})
        args = ", ".join(f"{k}={v!r}" for k, v in params.items())
        lines.append(f"    ({name!r}, {name}({args})),")
    lines.append("]")
    lines.append("")
    lines.append("results = train_and_evaluate(X_train, y_train, X_test, y_test, models)")
    lines.append("leaderboard = compare_models(results)")

    best_model = (result_data or {}).get("best_model")
    model_path = (result_data or {}).get("model_path")
    if best_model:
        lines.append(f"# Model tốt nhất: {best_model}" + (f" (đã lưu tại {model_path})" if model_path else ""))

    return "\n".join(lines) + "\n"
