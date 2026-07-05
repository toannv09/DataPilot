"""EDA Agent — orchestrate file_detector -> eda_planner -> tool execution -> insight_generator."""

import pandas as pd

from agents.base_agent import AgentResult, BaseAgent
from agents.eda_planner import plan as eda_plan
from agents.file_detector import detect as detect_files
from agents.hypothesis_generator import generate_hypotheses
from agents.insight_generator import generate as generate_insight
from agents.question_generator import generate_questions
from tools import profiler, quality_checker, relationship, scorer, stats_engine, viz_engine
from tools.file_merger import merge_files
from tools.schema_analyzer import detect_datetime_columns

TOOL_REGISTRY = {
    "check_missing": quality_checker.check_missing,
    "check_duplicates": quality_checker.check_duplicates,
    "check_outliers_iqr": quality_checker.check_outliers_iqr,
    "check_outliers_rolling": quality_checker.check_outliers_rolling,
    "check_type_mismatch": quality_checker.check_type_mismatch,
    "basic_stats": stats_engine.basic_stats,
    "skewness_kurtosis": stats_engine.skewness_kurtosis,
    "correlation_matrix": stats_engine.correlation_matrix,
    "time_series_decompose": stats_engine.time_series_decompose,
    "hourly_pattern": stats_engine.hourly_pattern,
    "weekly_pattern": stats_engine.weekly_pattern,
    "monthly_pattern": stats_engine.monthly_pattern,
    "lag_correlation": stats_engine.lag_correlation,
    "spearman_correlation": stats_engine.spearman_correlation,
    "normality_test": stats_engine.normality_test,
    "group_stats": stats_engine.group_stats,
    "mutual_info_scores": relationship.mutual_info_scores,
    "plot_distribution": viz_engine.plot_distribution,
    "plot_heatmap": viz_engine.plot_heatmap,
    "plot_time_series": viz_engine.plot_time_series,
    "plot_boxplot": viz_engine.plot_boxplot,
    "plot_seasonal_pattern": viz_engine.plot_seasonal_pattern,
    "plot_missing_heatmap": viz_engine.plot_missing_heatmap,
    "plot_decomposition": viz_engine.plot_decomposition,
    "plot_scatter": viz_engine.plot_scatter,
    "plot_violin": viz_engine.plot_violin,
    "plot_boxplot_by": viz_engine.plot_boxplot_by,
    "plot_mi_scores": viz_engine.plot_mi_scores,
    "plot_pairplot": viz_engine.plot_pairplot,
}

CHART_TOOLS = {
    "plot_distribution", "plot_heatmap", "plot_time_series", "plot_boxplot",
    "plot_seasonal_pattern", "plot_missing_heatmap", "plot_decomposition",
    "plot_scatter", "plot_violin", "plot_boxplot_by", "plot_mi_scores", "plot_pairplot",
}

# Chart có tỷ lệ/độ phức tạp không hợp với lưới 2 cột đồng nhất (quá rộng — time series/lag
# correlation; hoặc nhiều panel con — pairplot/decomposition/missing_heatmap) — hiển thị
# full-width ở UI thay vì bị bóp nhỏ chung 1 cột.
WIDE_CHART_TOOLS = {
    "plot_time_series", "plot_lag_correlation", "plot_pairplot",
    "plot_decomposition", "plot_missing_heatmap",
}

# Tool nào nhận "col" (1 cột), "cols" (danh sách cột), hoặc không nhận cột nào.
NO_COLUMN_TOOLS = {"check_missing", "check_duplicates", "check_type_mismatch", "plot_missing_heatmap"}
COLS_LIST_TOOLS = {"basic_stats", "correlation_matrix", "spearman_correlation", "plot_heatmap", "plot_pairplot"}
TWO_COLUMN_TOOLS = {"lag_correlation", "plot_scatter"}
# Tool nhận (col, by) — col số + by categorical
COL_BY_TOOLS = {"group_stats", "plot_boxplot_by"}
# Tool nhận target_col — không normalize, giữ nguyên
TARGET_COL_TOOLS = {"mutual_info_scores", "plot_mi_scores"}

# Tool yêu cầu DatetimeIndex — sẽ bị skip nếu df không có
DATETIME_REQUIRED_TOOLS = {
    "plot_time_series", "plot_decomposition", "plot_seasonal_pattern",
    "time_series_decompose", "hourly_pattern", "weekly_pattern", "monthly_pattern",
    "lag_correlation", "check_outliers_rolling",
}

# Tool phân tích shape phân phối — vô nghĩa với cột nhị phân/ít giá trị (vd cờ 0/1)
DISTRIBUTION_SHAPE_TOOLS = {
    "plot_violin", "plot_boxplot", "plot_boxplot_by", "plot_distribution",
    "skewness_kurtosis", "normality_test",
}
MIN_UNIQUE_FOR_DISTRIBUTION = 5


def _col_has_enough_variety(df, col):
    try:
        return df[col].nunique(dropna=True) >= MIN_UNIQUE_FOR_DISTRIBUTION
    except Exception:
        return True

MAX_RETRIES = 3
MAX_RESULT_ROWS = 100

CAPTION_TEMPLATES = {
    "plot_distribution":    "Phân phối của cột {col}",
    "plot_time_series":     "Biến động {col} theo thời gian",
    "plot_heatmap":         "Ma trận tương quan (Pearson)",
    "plot_boxplot":         "Boxplot — {col}",
    "plot_decomposition":   "Phân rã trend/seasonality — {col}",
    "plot_seasonal_pattern":"Pattern theo {by} — {col}",
    "plot_missing_heatmap": "Bản đồ missing value",
    "plot_lag_correlation": "{col1} vs {col2} (lag correlation)",
    "plot_scatter":         "Scatter: {col1} vs {col2}",
    "plot_violin":          "Violin — {col}",
    "plot_boxplot_by":      "{col} theo nhóm {by}",
    "plot_mi_scores":       "Feature importance (Mutual Information) với target {target_col}",
    "plot_pairplot":        "Quan hệ đồng thời giữa nhiều biến số (pairplot)",
}


def _make_caption(tool_name, params):
    template = CAPTION_TEMPLATES.get(tool_name, tool_name.replace("_", " ").title())
    try:
        return template.format(**params)
    except KeyError:
        return template


def _normalize_params(tool_name, params):
    """Chuẩn hóa key tham số do LLM sinh ra (vd "column") về đúng tên tham số của tool."""
    params = dict(params)

    if tool_name in NO_COLUMN_TOOLS:
        for key in ("column", "columns", "col", "cols", "col1", "col2"):
            params.pop(key, None)
        return params

    if tool_name in TWO_COLUMN_TOOLS:
        if "column" in params and "col1" not in params:
            value = params.pop("column")
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                params["col1"], params["col2"] = value[0], value[1]
        if "columns" in params and "col1" not in params:
            value = params.pop("columns")
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                params["col1"], params["col2"] = value[0], value[1]
        return params

    if tool_name in COLS_LIST_TOOLS:
        for key in ("column", "col"):
            if key in params and "cols" not in params:
                value = params.pop(key)
                params["cols"] = value if isinstance(value, list) else [value]
        if "columns" in params and "cols" not in params:
            params["cols"] = params.pop("columns")
        return params

    if tool_name in COL_BY_TOOLS:
        # LLM đôi khi dùng "column", "group_by", "group", "category"
        for alias in ("column", "columns"):
            if alias in params and "col" not in params:
                params["col"] = params.pop(alias)
        for alias in ("group_by", "group", "category", "groupby"):
            if alias in params and "by" not in params:
                params["by"] = params.pop(alias)
        return params

    if tool_name in TARGET_COL_TOOLS:
        # Normalize "target", "col", "column" → "target_col"
        for alias in ("target", "col", "column"):
            if alias in params and "target_col" not in params:
                params["target_col"] = params.pop(alias)
        return params

    # Tool nhận 1 "col"
    for key in ("column", "columns"):
        if key in params and "col" not in params:
            value = params.pop(key)
            params["col"] = value[0] if isinstance(value, (list, tuple)) and value else value

    return params


_PHASE1_TOOLS = ["check_missing", "check_duplicates", "check_type_mismatch"]


def _run_phase1(df):
    """Chạy kiểm tra chất lượng cứng (không cần LLM). Trả về results và log.

    Ngoài check_missing/duplicates/type_mismatch/basic_stats, còn chạy CỨNG (không phụ thuộc
    LLM planner Phase 2 có chọn hay không):
    - check_outliers_iqr cho MỌI cột số — trước đây hoàn toàn tùy LLM chọn, có thể không bao
      giờ chạy dù dataset rõ ràng có outlier (stat-card "Outlier phát hiện" ở UI hay ra "—").
    - correlation_matrix (Pearson) cho mọi cột số nếu có ≥2 cột, kèm significance scoring
      ngay — để stat-card "Tương quan cao nhất" luôn có số liệu thật, không phụ thuộc planner.
    """
    results, log = {}, []
    numeric_cols = list(df.select_dtypes(include="number").columns)
    steps = [
        {"tool": "check_missing",      "params": {}},
        {"tool": "check_duplicates",    "params": {}},
        {"tool": "check_type_mismatch", "params": {}},
    ]
    if numeric_cols:
        steps.append({"tool": "basic_stats", "params": {"cols": numeric_cols}})
        for col in numeric_cols:
            steps.append({"tool": "check_outliers_iqr", "params": {"col": col}})
        if len(numeric_cols) >= 2:
            steps.append({"tool": "correlation_matrix", "params": {"cols": numeric_cols}})

    for step in steps:
        tool_name = step["tool"]
        params = step["params"]
        func = TOOL_REGISTRY.get(tool_name)
        if func is None:
            continue
        try:
            output = func(df, **params)
            result_key = _disambiguated_key(tool_name, params, results)
            results[result_key] = output.to_dict(orient="records") if isinstance(output, pd.DataFrame) else output
            _auto_score(results, tool_name, result_key, params, df)
            log.append({
                "step": tool_name, "params": params, "status": "success",
                "retry_count": 0, "result_key": result_key,
            })
        except Exception as e:
            log.append({"step": tool_name, "params": params, "status": "error", "error": str(e)})

    return results, log


MIN_COLS_FOR_PAIRPLOT = 3
MAX_PAIRPLOT_COLS = 5


def _select_pairplot_cols(df, numeric_cols, max_cols=MAX_PAIRPLOT_COLS):
    """Chọn cột số 'liên kết' nhiều nhất (trung bình |corr| cao nhất với cột khác) cho pairplot."""
    if len(numeric_cols) <= max_cols:
        return numeric_cols
    try:
        corr = df[numeric_cols].corr().abs()
        avg_corr = (corr.sum(axis=1) - 1) / max(len(numeric_cols) - 1, 1)
        return avg_corr.sort_values(ascending=False).head(max_cols).index.tolist()
    except Exception:
        return numeric_cols[:max_cols]


def _trigger_rules(phase1_results, df):
    """Sinh extra steps dựa trên kết quả Phase 1 — chạy chắc chắn, không phụ thuộc LLM chọn."""
    extra = []
    missing = phase1_results.get("check_missing", {})
    total_missing = missing.get("total_missing", 0) if isinstance(missing, dict) else 0
    n_rows = len(df)
    if n_rows > 0 and total_missing / max(n_rows, 1) > 0.15:
        extra.append({"tool": "plot_missing_heatmap", "params": {}})

    basic = phase1_results.get("basic_stats", {})
    if isinstance(basic, dict):
        # basic_stats() không tính skewness (chỉ mean/median/std/min/max/p25/p75/p95) — tính
        # trực tiếp từ df, chọn cột lệch NHẤT (không phải cột đầu tiên vượt ngưỡng theo thứ
        # tự dict, vốn phụ thuộc tình cờ thứ tự cột trong file).
        most_skewed_col, most_skewed_val = None, 0.0
        for col in basic.keys():
            # Cờ nhị phân (0/1) mất cân bằng (vd attrition hiếm) có thể có |skewness| RẤT cao
            # về mặt số học nhưng vẽ violin cho nó vô nghĩa — loại trước, không chỉ dựa vào
            # DISTRIBUTION_SHAPE_TOOLS guard ở execute_plan() (lúc đó đã phí mất slot trigger).
            if not _col_has_enough_variety(df, col):
                continue
            try:
                skew = df[col].dropna().skew()
            except Exception:
                continue
            if abs(skew) > 1.5 and abs(skew) > abs(most_skewed_val):
                most_skewed_col, most_skewed_val = col, skew
        if most_skewed_col:
            extra.append({"tool": "plot_violin", "params": {"col": most_skewed_col}})

        numeric_cols = list(basic.keys())
        if len(numeric_cols) >= MIN_COLS_FOR_PAIRPLOT:
            pairplot_cols = _select_pairplot_cols(df, numeric_cols)
            extra.append({"tool": "plot_pairplot", "params": {"cols": pairplot_cols}})

    return extra


def _summarize_phase1(phase1_results, extra_steps=None):
    """Tóm tắt phase1 results + các bước đã trigger tự động thành chuỗi ngắn cho planner."""
    lines = []
    missing = phase1_results.get("check_missing", {})
    if isinstance(missing, dict):
        lines.append(f"- Đã check_missing: tổng {missing.get('total_missing', 0)} giá trị thiếu")
    dups = phase1_results.get("check_duplicates", {})
    if isinstance(dups, dict):
        lines.append(f"- Đã check_duplicates: {dups.get('n_duplicates', 0)} bản ghi trùng")
    if "basic_stats" in phase1_results:
        lines.append("- Đã basic_stats: đã thống kê mô tả các cột số")
    if "check_type_mismatch" in phase1_results:
        lines.append("- Đã check_type_mismatch")
    done_tools = list(_PHASE1_TOOLS) + ["basic_stats"]

    n_outlier_cols = len(results_for_tool(phase1_results, "check_outliers_iqr"))
    if n_outlier_cols:
        lines.append(f"- Đã check_outliers_iqr cho TẤT CẢ {n_outlier_cols} cột số — KHÔNG cần gọi lại")
        done_tools.append("check_outliers_iqr")
    if "correlation_matrix" in phase1_results:
        lines.append(
            "- Đã correlation_matrix (Pearson) cho tất cả cột số — chỉ gọi lại nếu muốn xem "
            "tập cột con khác hoặc dùng Spearman"
        )
        done_tools.append("correlation_matrix")

    if extra_steps:
        triggered_tools = [s["tool"] for s in extra_steps]
        lines.append(f"- Đã tự động trigger: {', '.join(triggered_tools)} (theo rule dựa trên kết quả Phase 1)")
        done_tools += triggered_tools

    lines.append(f"  → Không sinh lại các tool: {', '.join(done_tools)}")
    return "\n".join(lines) if lines else "(chưa có)"


_TREND_TOOLS = {"hourly_pattern", "weekly_pattern", "monthly_pattern"}
_CORR_TOOLS = {"correlation_matrix", "spearman_correlation"}
_GROUP_TOOLS = {"group_stats"}


def _disambiguated_key(tool_name, params, results):
    """Key để lưu vào `results` — giữ nguyên `tool_name` cho lần gọi đầu (tương thích ngược
    với mọi nơi đang đọc results[tool_name] trực tiếp: insight_generator, UI stat-card,
    code_export). Nếu planner gọi LẠI cùng tool với param khác (vd check_outliers_iqr cho 2
    cột khác nhau), lần gọi sau dùng key riêng theo param — tránh bug cũ: `results` chỉ key
    theo tên tool nên lần gọi sau âm thầm đè mất kết quả lần gọi trước.
    """
    if tool_name not in results:
        return tool_name
    parts = []
    for v in params.values():
        if isinstance(v, (list, tuple)):
            parts.append("-".join(str(x) for x in v))
        elif v is not None:
            parts.append(str(v))
    suffix = "_".join(parts) or "x"
    key = f"{tool_name}__{suffix}"
    n = 2
    while key in results:
        key = f"{tool_name}__{suffix}_{n}"
        n += 1
    return key


def results_for_tool(results, tool_name):
    """Trả về list giá trị trong `results` thuộc về `tool_name` — gồm key gốc (lần gọi đầu)
    và mọi key disambiguated `tool_name__...` (lần gọi sau, xem `_disambiguated_key`). Dùng
    để gộp đủ kết quả khi tool bị gọi nhiều lần, không chỉ đọc lần gọi đầu.
    """
    prefix = f"{tool_name}__"
    return [v for k, v in results.items() if k == tool_name or k.startswith(prefix)]


def significant_pairs_for_tool(results, tool_name):
    """Gộp tất cả '<tool_name>[...]_significant_pairs' — kể cả khi tool tương quan bị gọi
    nhiều lần với `cols` khác nhau (mỗi lần là 1 key riêng theo `_disambiguated_key`).
    """
    suffix = "_significant_pairs"
    pairs = []
    for k, v in results.items():
        if not k.endswith(suffix):
            continue
        if k == f"{tool_name}{suffix}" or k.startswith(f"{tool_name}__"):
            pairs.extend(v or [])
    return pairs


def _auto_score(results, tool_name, result_key, params, df):
    """Gắn significance score vào results sau khi tool chạy xong — lưu theo `result_key`
    (không phải `tool_name` thô) để không bị đè khi tool chạy nhiều lần với param khác.
    """
    try:
        if tool_name in _TREND_TOOLS:
            col = params.get("col")
            data = results.get(result_key)
            if col and isinstance(data, list) and data:
                series = pd.DataFrame(data).iloc[:, -1]  # cột giá trị cuối
                s = scorer.score_trend(series)
                if s:
                    results[f"{result_key}_significance"] = s

        elif tool_name in _CORR_TOOLS:
            cols = params.get("cols")
            method = "spearman" if tool_name == "spearman_correlation" else "pearson"
            if cols:
                candidates = scorer.top_significant_correlations(df, cols, n=3, method=method)
                if candidates:
                    results[f"{result_key}_significant_pairs"] = candidates

        elif tool_name in _GROUP_TOOLS:
            col = params.get("col")
            by = params.get("by")
            if col and by:
                s = scorer.score_group_diff(df, col, by)
                if s:
                    results[f"{result_key}_significance"] = s
    except Exception:
        pass  # scoring là optional, không được làm crash execute_plan


class EDAAgent(BaseAgent):
    def __init__(self, context):
        super().__init__(context)
        self.df = None
        self.code_meta = {}

    def detect(self):
        """Đọc schema, tìm join key, đề xuất merge plan (bước 2 trong FLOW.md)."""
        return detect_files(self.context.files, self.context.file_paths)

    def _prepare_dataframe(self, detection):
        """Merge file (nếu user đồng ý) và set datetime index nếu có (bước 3)."""
        files = self.context.files

        if len(files) == 1:
            df = next(iter(files.values())).copy()
            self.code_meta = {"file_names": list(files.keys()), "merge_applied": False}
        else:
            merge_plan = detection["merge_plan"]
            if merge_plan.can_merge and self.context.extra.get("merge_confirmed", True):
                df = merge_files(files, merge_plan)
                self.code_meta = {
                    "file_names": list(files.keys()),
                    "merge_applied": True,
                    "merge_groups": merge_plan.groups,
                    "merge_reason": merge_plan.reason,
                }
            else:
                df = next(iter(files.values())).copy()
                self.code_meta = {"file_names": [next(iter(files.keys()))], "merge_applied": False}

        dt_cols = detect_datetime_columns(df)
        if dt_cols:
            col = dt_cols[0]
            df[col] = pd.to_datetime(df[col])
            df = df.set_index(col).sort_index()
            self.code_meta["datetime_col"] = col
        else:
            self.code_meta["datetime_col"] = None

        return df

    def execute_plan(self, plan_data, df):
        """Thực thi từng tool call trong plan, log lại từng bước (bước 5)."""
        results = {}
        charts = []
        log = []
        chart_id_counter = 0
        # Chữ ký (tool, params) các chart đã vẽ — chặn LLM planner gọi lại đúng y 1 chart đã có
        # (vd trigger đã vẽ plot_pairplot(cols=X) nhưng planner KHÔNG tuân thủ phase1_summary,
        # tự gọi lại đúng cols đó lần 2) — nguyên tắc "không tin LLM tuân thủ 100% prompt, phải
        # có guard runtime" giống DATETIME_REQUIRED_TOOLS/DISTRIBUTION_SHAPE_TOOLS bên dưới.
        seen_chart_signatures = set()

        for step in plan_data.get("steps", []):
            tool_name = step.get("tool")
            params = step.get("params", {})
            source = step.get("source", "planner")
            params = {k: v for k, v in params.items() if k not in ("df", "dataset", "data")}
            params = _normalize_params(tool_name, params)
            func = TOOL_REGISTRY.get(tool_name)

            if func is None:
                log.append({"step": tool_name, "params": params, "status": "skipped", "reason": "tool không tồn tại"})
                continue

            if tool_name in CHART_TOOLS:
                chart_sig = (tool_name, tuple(sorted(
                    (k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in params.items()
                )))
                if chart_sig in seen_chart_signatures:
                    log.append({
                        "step": tool_name, "params": params, "status": "skipped",
                        "reason": "chart giống hệt (cùng tool + cùng params) đã chạy trước đó",
                    })
                    continue

            if tool_name in DATETIME_REQUIRED_TOOLS and not isinstance(df.index, pd.DatetimeIndex):
                log.append({"step": tool_name, "params": params, "status": "skipped", "reason": "tool yêu cầu DatetimeIndex"})
                continue

            if tool_name in DISTRIBUTION_SHAPE_TOOLS and "col" in params:
                if params["col"] in df.columns and not _col_has_enough_variety(df, params["col"]):
                    log.append({
                        "step": tool_name, "params": params, "status": "skipped",
                        "reason": f"cột '{params['col']}' có quá ít giá trị duy nhất, không phù hợp phân tích phân phối",
                    })
                    continue

            for retry_count in range(MAX_RETRIES):
                try:
                    output = func(df, **params)
                    result_key = tool_name
                    if tool_name in CHART_TOOLS:
                        chart_entry = {"path": output, "caption": _make_caption(tool_name, params), "source": source}
                        if tool_name in WIDE_CHART_TOOLS:
                            chart_entry["wide"] = True
                        if source == "planner":
                            chart_id_counter += 1
                            chart_entry["id"] = chart_id_counter
                        charts.append(chart_entry)
                        seen_chart_signatures.add(chart_sig)
                    else:
                        # _disambiguated_key: nếu tool này đã chạy trước (vd check_outliers_iqr
                        # cho cột khác), dùng key riêng theo param — không đè mất kết quả cũ.
                        result_key = _disambiguated_key(tool_name, params, results)
                        if isinstance(output, pd.DataFrame):
                            if len(output) > MAX_RESULT_ROWS:
                                results[result_key] = {
                                    "data": output.head(MAX_RESULT_ROWS).to_dict(orient="records"),
                                    "truncated": True,
                                    "total_rows": len(output),
                                }
                            else:
                                results[result_key] = output.to_dict(orient="records")
                        else:
                            results[result_key] = output

                        _auto_score(results, tool_name, result_key, params, df)

                    log.append({
                        "step": tool_name, "params": params, "status": "success",
                        "retry_count": retry_count, "result_key": result_key,
                    })
                    break
                except Exception as e:
                    if retry_count == MAX_RETRIES - 1:
                        log.append({"step": tool_name, "params": params, "status": "error", "error": str(e)})

        return results, charts, log

    async def run(self, context=None):
        context = context or self.context
        self._status = "running"

        from mlops import tracker
        tracker.init_run(context.experiment_type, {"files": list(context.files.keys())})

        try:
            detection = self.detect()
            self.df = self._prepare_dataframe(detection)
            has_datetime_index = isinstance(self.df.index, pd.DatetimeIndex)

            phase1_results, phase1_log = _run_phase1(self.df)
            extra_steps = _trigger_rules(phase1_results, self.df)
            for step in extra_steps:
                step["source"] = "trigger"  # chart tổng quan — không cần LLM gắn thẻ liên kết insight
            phase1_summary = _summarize_phase1(phase1_results, extra_steps)

            profiling_ctx = profiler.profiling_to_context(profiler.run_profiling(self.df))

            # Sinh hypothesis TRƯỚC khi plan, để planner sinh đúng bước kiểm chứng
            hypotheses = generate_hypotheses(
                detection["schemas"],
                context.domain_context,
                user_query=context.user_query,
                profiling_context=profiling_ctx,
            )

            question_data = generate_questions(
                detection["schemas"],
                user_query=context.user_query,
                domain_context=context.domain_context,
                has_datetime=has_datetime_index,
                profiling_context=profiling_ctx,
            )
            questions = question_data.get("questions", [])
            enriched_query = context.user_query or ""
            if questions:
                enriched_query = (
                    enriched_query + "\n\nCác câu hỏi cần trả lời:\n"
                    + "\n".join(f"- {q}" for q in questions)
                ).strip()
            if hypotheses:
                enriched_query = (
                    enriched_query + "\n\nGiả thuyết cần kiểm chứng bằng dữ liệu (PHẢI sinh bước phân tích để test, "
                    "vd: group_stats/correlation_matrix/normality_test với đúng cột liên quan):\n"
                    + "\n".join(f"- {h}" for h in hypotheses)
                ).strip()

            plan_data = eda_plan(
                enriched_query,
                detection["schemas"],
                context.domain_context,
                available_columns=list(self.df.columns),
                has_datetime_index=has_datetime_index,
                phase1_summary=phase1_summary,
            )
            if extra_steps:
                plan_data["steps"] = extra_steps + plan_data.get("steps", [])

            phase2_results, charts, phase2_log = self.execute_plan(plan_data, self.df)

            results = {**phase1_results, **phase2_results}
            log = phase1_log + phase2_log
            insights = generate_insight(results, context.domain_context, hypotheses=hypotheses, charts=charts)

            self._status = "done"
            return AgentResult(
                success=True,
                summary=plan_data.get("explanation") if isinstance(plan_data.get("explanation"), str) else "",
                data={"results": results, "merge_info": detection, "code_meta": self.code_meta},
                charts=charts,
                insights=insights,
                log=log,
            )
        except Exception as e:
            self._status = "error"
            return AgentResult(success=False, error=str(e))
        finally:
            tracker.finish_run()

    async def get_status(self):
        return self._status
