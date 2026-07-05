"""Sinh lại code Python từ log/config THỰC TẾ đã chạy — dùng cho nút 'Xem/tải code' ở UI.

Không dùng LLM viết lại — code sinh ra map trực tiếp 1:1 với tool/config đã thực thi
(lấy từ result.log / result.data["config"]), đảm bảo đúng với cái đã chạy, không suy diễn.
"""


def _resolve_tool_func(tool_name):
    from agents.eda_agent import TOOL_REGISTRY

    return TOOL_REGISTRY.get(tool_name)


def _corr_tools():
    from agents.eda_agent import _CORR_TOOLS

    return _CORR_TOOLS


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


def _eda_data_setup_lines(code_meta):
    """Sinh lại đúng bước chuẩn bị df đã chạy thật: merge nhiều file (nếu có) + set datetime
    index (nếu agent đã tự phát hiện cột thời gian) — lấy từ EDAAgent.code_meta.
    """
    code_meta = code_meta or {}
    file_names = code_meta.get("file_names") or ["your_file.csv"]
    merge_applied = bool(code_meta.get("merge_applied")) and len(file_names) > 1
    datetime_col = code_meta.get("datetime_col")

    lines = []
    if merge_applied:
        lines.append("files = {")
        for name in file_names:
            lines.append(f"    {name!r}: pd.read_csv({name!r}),")
        lines.append("}")
        lines.append("merge_plan = MergePlan(")
        lines.append("    can_merge=True,")
        lines.append(f"    groups={code_meta.get('merge_groups', [])!r},")
        lines.append(f"    reason={code_meta.get('merge_reason', '')!r},")
        lines.append(")")
        lines.append("df = merge_files(files, merge_plan)")
    else:
        lines.append(f"df = pd.read_csv({file_names[0]!r})  # thay bằng file dữ liệu của bạn")

    if datetime_col:
        lines.append(f"df[{datetime_col!r}] = pd.to_datetime(df[{datetime_col!r}])")
        lines.append(f"df = df.set_index({datetime_col!r}).sort_index()")

    return lines, merge_applied


def eda_log_to_code(log, results=None, code_meta=None):
    """Sinh code Python từ log thực thi EDA — chỉ lấy step status='success' (bỏ skipped/error).

    Chèn comment theo nhóm (kiểm tra chất lượng / thống kê / tương quan / time series /
    trực quan hóa) để dễ đọc — comment chỉ mang tính phân nhóm, không phải mô tả từng bước.

    results: result.data["results"] — dùng để biết tool tương quan nào có sinh ra
    "*_significant_pairs" (significance scoring), để sinh lại đúng bước đó.
    code_meta: result.data["code_meta"] — thông tin merge file / datetime index thực tế đã dùng
    (từ EDAAgent._prepare_dataframe), để df dựng lại đúng với cái đã chạy thật.
    """
    results = results or {}
    used_tools = []
    used_scorer = False
    call_lines = []
    prev_category = None
    corr_tools = _corr_tools()
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

        params = entry.get("params", {})
        call_lines.append(_format_call(tool_name, params))

        # result_key: key thật đã lưu vào results["..."] cho ĐÚNG lần gọi này — không phải
        # luôn là tool_name, vì tool tương quan gọi lại với cols khác sẽ có key riêng
        # (xem agents/eda_agent.py:_disambiguated_key, tránh bug cũ đè mất kết quả lần trước).
        result_key = entry.get("result_key", tool_name)
        if tool_name in corr_tools and results.get(f"{result_key}_significant_pairs"):
            method = "spearman" if tool_name == "spearman_correlation" else "pearson"
            cols = params.get("cols", [])
            call_lines.append(
                f"significant_pairs = top_significant_correlations(df, cols={cols!r}, n=3, method={method!r})"
            )
            used_scorer = True

    if not call_lines:
        return None

    imports_by_module = {}
    for tool_name in used_tools:
        func = _resolve_tool_func(tool_name)
        imports_by_module.setdefault(func.__module__, set()).add(func.__name__)
    if used_scorer:
        imports_by_module.setdefault("tools.scorer", set()).add("top_significant_correlations")
    import_lines = [
        f"from {module} import {', '.join(sorted(names))}"
        for module, names in sorted(imports_by_module.items())
    ]

    setup_lines, merge_applied = _eda_data_setup_lines(code_meta)

    header = ["import pandas as pd"]
    if merge_applied:
        header.append("from tools.file_merger import merge_files")
        header.append("from tools.schema_analyzer import MergePlan")
    header += import_lines
    header.append("")
    header += setup_lines
    header.append("")

    return "\n".join(header + call_lines) + "\n"


def preprocessing_config_to_code(cfg, target_col=None, steps=None, file_name=None):
    """Sinh code Python từ config thực tế PreprocessingAgent đã dùng cho PreprocessingPipeline.

    steps: list[str] — mô tả tiếng Việt từng việc đã làm (PreprocessingAgent.steps_log), chèn
    thành comment phía trên lệnh fit_transform để dễ hiểu — vẫn chỉ 1 lệnh thật, không bịa thêm.
    file_name: tên file dữ liệu thực tế đã chạy (context.files), để dòng đọc file đúng — thiếu
    dòng này code sẽ NameError vì `df` chưa từng được định nghĩa.
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

    file_name = file_name or "your_file.csv"
    return (
        "import pandas as pd\n"
        "from tools.ml.pipeline import PreprocessingPipeline\n\n"
        f"df = pd.read_csv({file_name!r})  # thay bằng file dữ liệu của bạn\n\n"
        f"{comment_block}"
        "pipeline = PreprocessingPipeline()\n"
        "df_processed = pipeline.fit_transform(\n"
        "    df,\n"
        f"    {args_block},\n"
        ")\n"
    )


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


def training_log_to_code(result_data, log, target_col=None, file_name=None):
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
        f"df = pd.read_csv({(file_name or 'your_file.csv')!r})  # thay bằng file dữ liệu của bạn",
        'df_numeric_raw = df.select_dtypes(include="number").copy()',
        "df_numeric = df_numeric_raw.copy()",
        "",
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
            lines.append("# Dùng df_numeric_raw (còn NaN) để NumericScaler tự ghi nhận fill_values,")
            lines.append("# giống đúng lúc chạy thật (không scale trên bản đã median-fill ở trên).")
            lines.append("scaler = NumericScaler()")
            lines.append("df_scaled = scaler.fit_transform(df_numeric_raw)")
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
