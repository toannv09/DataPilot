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
    """Chạy kiểm tra chất lượng cứng (không cần LLM). Trả về results và log."""
    results, log = {}, []
    numeric_cols = list(df.select_dtypes(include="number").columns)
    steps = [
        {"tool": "check_missing",      "params": {}},
        {"tool": "check_duplicates",    "params": {}},
        {"tool": "check_type_mismatch", "params": {}},
    ]
    if numeric_cols:
        steps.append({"tool": "basic_stats", "params": {"cols": numeric_cols}})

    for step in steps:
        tool_name = step["tool"]
        params = step["params"]
        func = TOOL_REGISTRY.get(tool_name)
        if func is None:
            continue
        try:
            output = func(df, **params)
            results[tool_name] = output.to_dict(orient="records") if isinstance(output, pd.DataFrame) else output
            log.append({"step": tool_name, "params": params, "status": "success", "retry_count": 0})
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
        for col, stats in basic.items():
            if isinstance(stats, dict) and abs(stats.get("skewness", 0) if "skewness" in stats else 0) > 1.5:
                extra.append({"tool": "plot_violin", "params": {"col": col}})
                break  # chỉ thêm 1 col lệch nhất

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

    if extra_steps:
        triggered_tools = [s["tool"] for s in extra_steps]
        lines.append(f"- Đã tự động trigger: {', '.join(triggered_tools)} (theo rule dựa trên kết quả Phase 1)")
        done_tools += triggered_tools

    lines.append(f"  → Không sinh lại các tool: {', '.join(done_tools)}")
    return "\n".join(lines) if lines else "(chưa có)"


_TREND_TOOLS = {"hourly_pattern", "weekly_pattern", "monthly_pattern"}
_CORR_TOOLS = {"correlation_matrix", "spearman_correlation"}
_GROUP_TOOLS = {"group_stats"}


def _auto_score(results, tool_name, params, df):
    """Gắn significance score vào results sau khi tool chạy xong."""
    try:
        if tool_name in _TREND_TOOLS:
            col = params.get("col")
            data = results.get(tool_name)
            if col and isinstance(data, list) and data:
                series = pd.DataFrame(data).iloc[:, -1]  # cột giá trị cuối
                s = scorer.score_trend(series)
                if s:
                    results[f"{tool_name}_significance"] = s

        elif tool_name in _CORR_TOOLS:
            data = results.get(tool_name)
            n = len(df)
            if isinstance(data, list):
                seen_pairs = set()
                candidates = []
                for row in data:
                    if not row:
                        continue
                    # to_dict(orient="records") mất tên dòng — suy ra từ vị trí đường chéo (=1.0)
                    diag = [k for k, v in row.items() if isinstance(v, (int, float)) and abs(v - 1.0) < 1e-9]
                    col_name = diag[0] if diag else None
                    if col_name is None:
                        continue
                    for other_col, r_val in row.items():
                        if other_col == col_name or not isinstance(r_val, (int, float)):
                            continue
                        pair_key = frozenset((col_name, other_col))
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)
                        s = scorer.score_pearson(r_val, n)
                        if s and s["significant"] and abs(r_val) > 0.3:
                            candidates.append({"col1": col_name, "col2": other_col, **s})
                if candidates:
                    candidates.sort(key=lambda p: -abs(p["r"]))
                    results[f"{tool_name}_significant_pairs"] = candidates[:3]

        elif tool_name in _GROUP_TOOLS:
            col = params.get("col")
            by = params.get("by")
            if col and by:
                s = scorer.score_group_diff(df, col, by)
                if s:
                    results[f"{tool_name}_significance"] = s
    except Exception:
        pass  # scoring là optional, không được làm crash execute_plan


class EDAAgent(BaseAgent):
    def __init__(self, context):
        super().__init__(context)
        self.df = None

    def detect(self):
        """Đọc schema, tìm join key, đề xuất merge plan (bước 2 trong FLOW.md)."""
        return detect_files(self.context.files, self.context.file_paths)

    def _prepare_dataframe(self, detection):
        """Merge file (nếu user đồng ý) và set datetime index nếu có (bước 3)."""
        files = self.context.files

        if len(files) == 1:
            df = next(iter(files.values())).copy()
        else:
            merge_plan = detection["merge_plan"]
            if merge_plan.can_merge and self.context.extra.get("merge_confirmed", True):
                df = merge_files(files, merge_plan)
            else:
                df = next(iter(files.values())).copy()

        dt_cols = detect_datetime_columns(df)
        if dt_cols:
            col = dt_cols[0]
            df[col] = pd.to_datetime(df[col])
            df = df.set_index(col).sort_index()

        return df

    def execute_plan(self, plan_data, df):
        """Thực thi từng tool call trong plan, log lại từng bước (bước 5)."""
        results = {}
        charts = []
        log = []
        chart_id_counter = 0

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
                    if tool_name in CHART_TOOLS:
                        chart_entry = {"path": output, "caption": _make_caption(tool_name, params), "source": source}
                        if source == "planner":
                            chart_id_counter += 1
                            chart_entry["id"] = chart_id_counter
                        charts.append(chart_entry)
                    elif isinstance(output, pd.DataFrame):
                        if len(output) > MAX_RESULT_ROWS:
                            results[tool_name] = {
                                "data": output.head(MAX_RESULT_ROWS).to_dict(orient="records"),
                                "truncated": True,
                                "total_rows": len(output),
                            }
                        else:
                            results[tool_name] = output.to_dict(orient="records")
                    else:
                        results[tool_name] = output

                    # Auto-score: gắn p-value / significance vào kết quả thống kê
                    _auto_score(results, tool_name, params, df)

                    log.append({"step": tool_name, "params": params, "status": "success", "retry_count": retry_count})
                    break
                except Exception as e:
                    if retry_count == MAX_RETRIES - 1:
                        log.append({"step": tool_name, "params": params, "status": "error", "error": str(e)})

        return results, charts, log

    async def run(self, context=None):
        context = context or self.context
        self._status = "running"

        try:
            detection = self.detect()
            self.df = self._prepare_dataframe(detection)
            has_datetime_index = isinstance(self.df.index, pd.DatetimeIndex)

            # Phase 1: kiểm tra chất lượng cứng + profiling (không cần LLM)
            phase1_results, phase1_log = _run_phase1(self.df)
            extra_steps = _trigger_rules(phase1_results, self.df)
            for step in extra_steps:
                step["source"] = "trigger"  # chart tổng quan — không cần LLM gắn thẻ liên kết insight
            phase1_summary = _summarize_phase1(phase1_results, extra_steps)

            # ydata-profiling: chạy nhanh, lấy context bổ sung (lỗi thì bỏ qua)
            profiling_ctx = profiler.profiling_to_context(profiler.run_profiling(self.df))

            # Sinh hypothesis TRƯỚC khi plan, để planner sinh đúng bước kiểm chứng
            hypotheses = generate_hypotheses(
                detection["schemas"],
                context.domain_context,
                user_query=context.user_query,
                profiling_context=profiling_ctx,
            )

            # Sinh câu hỏi phân tích từ schema, gộp vào query
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

            # Phase 2: LLM lập kế hoạch với context từ Phase 1
            plan_data = eda_plan(
                enriched_query,
                detection["schemas"],
                context.domain_context,
                available_columns=list(self.df.columns),
                has_datetime_index=has_datetime_index,
                phase1_summary=phase1_summary,
            )
            # Ghép trigger steps vào đầu plan Phase 2
            if extra_steps:
                plan_data["steps"] = extra_steps + plan_data.get("steps", [])

            # Thực thi Phase 2
            phase2_results, charts, phase2_log = self.execute_plan(plan_data, self.df)

            # Gộp kết quả hai phase, phase1 làm nền cho insight
            results = {**phase1_results, **phase2_results}
            log = phase1_log + phase2_log
            insights = generate_insight(results, context.domain_context, hypotheses=hypotheses, charts=charts)

            self._status = "done"
            return AgentResult(
                success=True,
                summary=plan_data.get("explanation", ""),
                data={"results": results, "merge_info": detection},
                charts=charts,
                insights=insights,
                log=log,
            )
        except Exception as e:
            self._status = "error"
            return AgentResult(success=False, error=str(e))

    async def get_status(self):
        return self._status
