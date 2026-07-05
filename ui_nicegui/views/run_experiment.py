"""Chạy experiment — chat interface, hiển thị insight/biểu đồ, human-in-the-loop.

Tương đương ui/views/run_experiment.py (Streamlit). Khác biệt kiến trúc quan trọng:
Streamlit rerun toàn bộ script mỗi lần tương tác; NiceGUI event-driven nên ở đây dùng pattern
"clear() + rebuild" trên 1 container (`body`) để mô phỏng lại đúng hiệu ứng st.rerun().

`rerun()` và `render_body()` đều là async — MỌI handler nào (trực tiếp hay gián tiếp) dẫn tới
gọi rerun() đều phải là `async def` (không dùng lambda, lambda không await được), để tránh
chạy code thêm UI ngoài context `with body:` đúng lúc (NiceGUI quản lý "container hiện tại"
theo async-context khi dispatch event/click — async def giữ đúng context, còn ui.timer/callback
rời rạc thì không đảm bảo).
"""

import asyncio
import json
import os
from datetime import datetime

import pandas as pd
from nicegui import run as nicegui_run
from nicegui import ui

import state
import theme
from agents import report_generator
from agents.code_export import eda_log_to_code, preprocessing_config_to_code, training_log_to_code
from agents.eda_agent import results_for_tool, significant_pairs_for_tool
from agents.insight_generator import split_insight_by_charts
from agents.pipeline_agent import STAGES, PipelineAgent
from agents.router import route
from components.chart_viewer import render_charts
from components.header import render_breadcrumbs, render_chip, render_header
from components.result_widgets import info_box, progress_bar, progress_steps, safe_markdown, stat_card, terminal_log
from components.run_log import render_log
from llm.client import MODEL_DEFAULT, call_llm
from mlops.logger import ExecutionLogger
from tools.ml.trainer import HIGHER_IS_BETTER_METRICS

_AMBIGUOUS_QUERIES = {"phân tích", "xem", "check", "thử", "xem thử", "phân tích dữ liệu", ""}
EXPERIMENT_TYPE_TO_KIND = {
    "Khám phá dữ liệu": "eda",
    "Xử lý dữ liệu": "preprocessing",
    "Huấn luyện mô hình": "training",
    "Đánh giá mô hình": "evaluation",
    "Suy luận mô hình": "inference",
}
STAGE_LABELS = {
    "eda": "Khám phá dữ liệu (EDA)",
    "preprocessing": "Xử lý dữ liệu",
    "training": "Huấn luyện mô hình",
    "evaluation": "Đánh giá mô hình",
}

# Huấn luyện/Đánh giá/Suy luận chỉ dùng context.user_query để sinh lời GIẢI THÍCH của AI
# (xem ML_EXPLANATION_USER/EXPLAIN_PREDICTION_PROMPT) — model/metric/dự đoán được tính lại
# CHÍNH XÁC như cũ vì phụ thuộc context.extra (model/target/split...), không đọc user_query.
# Khác EDA/Xử lý dữ liệu — user_query ảnh hưởng trực tiếp đến plan/preprocessing_planner.
_EXPLANATION_ONLY_TYPES = {"Huấn luyện mô hình", "Đánh giá mô hình", "Suy luận mô hình"}
_EXPLANATION_ONLY_STAGES = {"training", "evaluation"}
MAX_FEEDBACK_CONTEXT_CHARS = 3000

AGENT_PHASES = {
    "Khám phá dữ liệu": [
        "Phát hiện schema & đề xuất merge",
        "Kiểm tra chất lượng dữ liệu",
        "Thống kê & tương quan",
        "Sinh biểu đồ trực quan",
        "Tổng hợp insight tiếng Việt",
    ],
    "Xử lý dữ liệu": ["Kiểm tra missing & outlier", "Mã hóa & chuẩn hóa cột", "Lưu dữ liệu đã xử lý"],
    "Huấn luyện mô hình": [
        "Tách train/test",
        "Huấn luyện các model baseline",
        "So sánh & chọn model tốt nhất",
        "Lưu model",
    ],
    "Đánh giá mô hình": ["Load model đã lưu", "Dự đoán trên dữ liệu test", "Tính chỉ số đánh giá", "Nhận xét từ AI"],
    "Suy luận mô hình": ["Load model đã lưu", "Dự đoán trên dữ liệu mới", "Giải thích kết quả"],
    "Tùy chỉnh": ["Agent đang xử lý câu hỏi của bạn"],
}

_METRIC_LABELS = {
    "rmse": "RMSE",
    "mae": "MAE",
    "r2": "R²",
    "accuracy": "Accuracy",
    "f1": "F1",
    "precision": "Precision",
    "recall": "Recall",
    "silhouette": "Silhouette",
    "inertia": "Inertia",
}

_SUMMARY_CARD_META = {
    "eda": ("auto_awesome", "#EE0033", "Tóm tắt kế hoạch phân tích", "Từ EDA Agent"),
    "preprocessing": ("auto_awesome", "#EE0033", "Mô tả các bước xử lý", "Từ Agent"),
    "training": ("auto_awesome", "#EE0033", "Nhận xét model", "Từ AI Agent"),
    "evaluation": ("auto_awesome", "#EE0033", "Nhận xét chất lượng model", "Từ AI Agent · trên tập test"),
    "inference": ("auto_awesome", "#EE0033", "Giải thích kết quả dự báo", "Từ AI Agent"),
}

_TABLE_CSS = """
.aeda-table thead tr th { background:#F7F7F8 !important; color:#44494D !important; font-weight:500 !important; }
.aeda-table tbody tr:nth-child(even) td { background:#fafafa; }
"""


def _detect_ambiguity(user_query):
    q = (user_query or "").strip().lower()
    return len(q) < 15 or q in _AMBIGUOUS_QUERIES


def _split_charts_by_source(charts):
    """Tách chart 'trigger' (tổng quan) khỏi 'planner' (có thể gắn thẻ insight)."""
    trigger = [c for c in (charts or []) if isinstance(c, dict) and c.get("source") == "trigger"]
    planner = [c for c in (charts or []) if not (isinstance(c, dict) and c.get("source") == "trigger")]
    return trigger, planner


def _format_metric(value):
    return f"{value:.3f}" if isinstance(value, (int, float)) else str(value)


def _df_table(df, max_rows=5):
    sample = df.head(max_rows).astype(str)
    columns = [{"name": c, "label": c, "field": c} for c in sample.columns]
    rows = sample.to_dict(orient="records")
    ui.table(columns=columns, rows=rows).classes("w-full aeda-table").props("flat dense")


def _render_explanation_only_note(applies):
    if not applies:
        return
    with ui.row().classes("items-start gap-2 mb-2 p-2 w-full").style(
        "background:#FFF8F0; border-left:3px solid #F57C00; border-radius:6px;"
    ):
        ui.icon("info", color="#F57C00").style("font-size:14px; margin-top:1px; flex-shrink:0;")
        ui.label(
            "Lưu ý: ở loại experiment này, góp ý chỉ ảnh hưởng phần GIẢI THÍCH của AI — model, "
            "metric hay dự đoán vẫn được tính lại y nguyên theo cấu hình cũ (split, model, target...). "
            "Muốn đổi model/cấu hình thật, hãy \"Quay lại\" và chỉnh ở bước Cấu hình."
        ).classes("text-xs text-gray-700")


def _card_header(icon, color, title, subtitle):
    with ui.row().classes("items-center gap-3 w-full pb-2 mb-2").style(
        "border-bottom: 0.5px solid rgba(0,0,0,0.07);"
    ):
        with ui.element("div").classes("flex items-center justify-center").style(
            f"background:{color}1A; color:{color}; width:30px; height:30px; flex-shrink:0; border-radius:7px;"
        ):
            ui.icon(icon, color=color).style("font-size:16px;")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("text-sm font-medium")
            if subtitle:
                ui.label(subtitle).classes("text-xs text-gray-400")


def _header_row(context, title, badge_text=None, right=None):
    with ui.row().classes("w-full items-center justify-between"):
        with ui.column().classes("gap-1"):
            with ui.row().classes("items-center gap-2"):
                ui.label(title).classes("text-base font-medium").style("color:#1a1a1a;")
                if badge_text:
                    ui.badge(badge_text, color="positive" if badge_text == "Thành công" else "negative").classes(
                        "text-xs px-2"
                    )
            with ui.row().classes("gap-2"):
                render_chip("database", context.problem_name, "#EE0033")
                render_chip("bar_chart", context.experiment_type, "#44494D")
        if right:
            with ui.row().classes("gap-2"):
                right()


def _go_to_report(context, result, report_path):
    """Tìm lại metadata (run_id/trạng thái/thời gian) của run vừa lưu để hiển thị ở sidebar
    trang /report — _save_run() đã ghi report_path vào đúng run đó nên match theo path là đủ,
    không cần truyền thêm run_id qua nhiều lớp closure."""
    run_meta = next(
        (r for r in state.get("runs", []) if r.get("report_path") == report_path),
        None,
    )
    state.set_value("report_path", report_path)
    state.set_value(
        "report_meta",
        {
            "problem": context.problem_name,
            "experiment_type": context.experiment_type,
            "run_id": run_meta.get("run_id") if run_meta else None,
            "status": "success" if result.success else "error",
            "duration_seconds": run_meta.get("duration_seconds") if run_meta else None,
        },
    )
    state.set_value("report_return_path", "/run-experiment")
    state.set_value(
        "report_breadcrumbs",
        [("Trang chủ", "/"), ("Cấu hình", "/experiment-config"), ("Kết quả", "/run-experiment")],
    )
    ui.navigate.to("/report")


def _result_header_actions(context, result, on_back):
    def render():
        report_path = (result.data or {}).get("report_path")
        if report_path:
            ui.button(
                "Xem báo cáo",
                icon="description",
                on_click=lambda: _go_to_report(context, result, report_path),
            ).props("outline color=grey-7")
        ui.button("Lịch sử", icon="history", on_click=lambda: ui.navigate.to("/run-history")).props(
            "outline color=grey-7"
        )
        ui.button("Quay lại", on_click=on_back).props("outline color=grey-7")

    return render


def _simple_loading_card(label):
    with ui.card().classes("w-full"):
        progress_steps([{"label": label, "status": "running"}])


_PHASE_TICK_SECONDS = 4.0
_PIPELINE_LOG_TICK_SECONDS = 2.0


def _safe_ticker(interval, callback):
    """ui.timer mà tự cancel() nếu callback lỗi — xảy ra khi client đã disconnect (đóng tab /
    điều hướng đi) giữa lúc agent vẫn đang chạy ở backend: zone.clear()/render() vào 1 element
    đã bị xoá sẽ raise, nếu không chặn thì NiceGUI cứ gọi lại callback lỗi mỗi interval mãi."""
    holder = {}

    def guarded():
        try:
            callback()
        except Exception:
            holder["timer"].cancel()

    holder["timer"] = ui.timer(interval, guarded)
    return holder["timer"]


def _agent_running_card(experiment_type):
    """Card 'tiến trình thực thi' cho agent đơn (EDA/preprocessing/training/evaluation/inference).

    agent.run() là MỘT lời gọi chặn duy nhất — backend không phát tín hiệu progress thật theo
    từng bước. Để khỏi đứng yên ở bước 1 suốt cả phút rồi nhảy thẳng qua kết quả (gây cảm giác
    UI "đứng"), tự chạy ui.timer cho list bước + nhật ký lần lượt tiến qua các phase đã biết,
    dừng lại ở phase cuối (không lặp lại) chờ kết quả thật.

    Trả về ui.timer — caller PHẢI gọi .cancel() ngay khi có kết quả thật, trước khi rerun().
    """
    phases = AGENT_PHASES.get(experiment_type, ["Agent đang xử lý..."])
    cursor = {"idx": 0}
    zone = ui.column().classes("w-full gap-3")

    def render():
        zone.clear()
        with zone:
            with ui.card().classes("w-full"):
                _card_header("autorenew", "#EE0033", "Tiến trình thực thi", f"Agent đang xử lý · {experiment_type}")
                steps = []
                for i, p in enumerate(phases):
                    if i < cursor["idx"]:
                        status = "done"
                    elif i == cursor["idx"]:
                        status = "running"
                    else:
                        status = "pending"
                    steps.append({"label": p, "status": status})
                progress_steps(steps)
                progress_bar(cursor["idx"] + 1, len(phases))
            with ui.card().classes("w-full"):
                _card_header("terminal", "#5F5E5A", "Nhật ký thực thi", "Log realtime từ agent")
                lines = [(f"{phases[i]}: hoàn thành", "done") for i in range(cursor["idx"])]
                lines.append((f"{phases[cursor['idx']]}: đang chạy...", "running"))
                terminal_log(lines)

    def tick():
        if cursor["idx"] < len(phases) - 1:
            cursor["idx"] += 1
        render()

    render()
    return _safe_ticker(_PHASE_TICK_SECONDS, tick)


def _pipeline_running_card(steps, stage_idx):
    """Card 'tiến trình thực thi' cho Full Pipeline. Step list theo STAGE là tiến trình THẬT
    (mỗi stage chỉ đổi done/running khi stage trước đó thực sự đã chạy xong) nên không cần giả
    lập — chỉ animate phần nhật ký (chấm "..." chạy) để khỏi trông như log đứng yên trong lúc
    chờ 1 stage (cũng là 1 lời gọi chặn duy nhất) chạy xong.
    """
    items = []
    for i, stage in enumerate(STAGES):
        if i < stage_idx:
            items.append({"label": STAGE_LABELS[stage], "status": "done", "subtext": "Hoàn thành"})
        elif i == stage_idx:
            items.append({"label": STAGE_LABELS[stage], "status": "running", "subtext": "Đang chạy"})
        else:
            items.append({"label": STAGE_LABELS[stage], "status": "pending", "subtext": "Chờ"})

    with ui.card().classes("w-full"):
        _card_header("autorenew", "#EE0033", "Tiến trình thực thi", "Pipeline đang chạy theo từng bước")
        progress_steps(items)
        progress_bar(min(stage_idx + 1, len(STAGES)), len(STAGES))

    log_zone = ui.column().classes("w-full gap-3")
    tick_state = {"n": 0}

    def render_log():
        log_zone.clear()
        with log_zone:
            with ui.card().classes("w-full"):
                _card_header("terminal", "#5F5E5A", "Nhật ký thực thi", "Log realtime từ agent")
                lines = []
                for stage in STAGES[:stage_idx]:
                    r = steps.get(stage)
                    if r:
                        lines.append((f"{STAGE_LABELS[stage]}: hoàn thành ({len(r.log)} bước)", "done"))
                if stage_idx < len(STAGES):
                    dots = "." * (1 + tick_state["n"] % 3)
                    lines.append((f"{STAGE_LABELS[STAGES[stage_idx]]}: đang chạy{dots}", "running"))
                terminal_log(lines)

    def tick():
        tick_state["n"] += 1
        render_log()

    render_log()
    return _safe_ticker(_PIPELINE_LOG_TICK_SECONDS, tick)


def render_insight_with_charts(insight_text, planner_charts):
    segments, used_ids = split_insight_by_charts(insight_text, planner_charts)
    for seg in segments:
        if seg["type"] == "text":
            safe_markdown(seg["content"])
        else:
            chart = seg["chart"]
            with ui.column().classes("w-full gap-1 p-2 mt-1 mb-2").style(
                "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.08); border-radius:8px;"
            ):
                ui.image(chart["path"]).classes("w-full" if chart.get("wide") else "max-w-xl")
                if chart.get("caption"):
                    ui.label(chart["caption"]).classes("text-xs text-gray-400 italic")

    leftover = [c for c in planner_charts if c.get("id") is not None and c["id"] not in used_ids]
    if leftover:
        ui.label("Biểu đồ khác:").classes("text-sm text-gray-500 mt-1")
        render_charts(leftover)


def render_code_export(kind, result, context):
    code_str = None
    if kind == "eda":
        data = result.data or {}
        code_str = eda_log_to_code(result.log, results=data.get("results"), code_meta=data.get("code_meta"))
    elif kind == "preprocessing":
        cfg = result.data.get("config") if result.data else None
        steps = result.data.get("steps") if result.data else None
        file_name = next(iter(context.files.keys()), None)
        code_str = preprocessing_config_to_code(
            cfg, target_col=context.extra.get("target_col"), steps=steps, file_name=file_name
        )
    elif kind == "training":
        file_name = next(iter(context.files.keys()), None)
        code_str = training_log_to_code(
            result.data, result.log, target_col=context.extra.get("target_col"), file_name=file_name
        )

    if not code_str:
        return

    with ui.card().classes("w-full"):
        _card_header("code", "#854F0B", "Code đã chạy", "Tái tạo lại kết quả hoàn toàn với script này")
        ui.code(code_str, language="python").classes("w-full")
        with ui.row().classes("gap-2 mt-2"):
            ui.button(
                "Tải file (.py)",
                icon="download",
                on_click=lambda: ui.download(code_str.encode("utf-8"), filename=f"{kind}_code.py"),
            ).props("outline color=grey-7")
            ui.button(
                "Copy code",
                icon="content_copy",
                on_click=lambda: ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(code_str)})"),
            ).props("outline color=grey-7")

            if kind == "preprocessing":
                processed_path = result.data.get("processed_path")
                if processed_path and os.path.exists(processed_path):
                    with open(processed_path, "rb") as f:
                        data = f.read()
                    ui.button(
                        "Tải CSV đã xử lý",
                        icon="table_chart",
                        on_click=lambda d=data, p=processed_path: ui.download(d, filename=os.path.basename(p)),
                    ).props("outline color=grey-7")
            elif kind == "training":
                model_path = result.data.get("model_path")
                if model_path and os.path.exists(model_path):
                    with open(model_path, "rb") as f:
                        data = f.read()
                    ui.button(
                        "Tải model (.pkl)",
                        icon="smart_toy",
                        on_click=lambda d=data, p=model_path: ui.download(d, filename=os.path.basename(p)),
                    ).props("outline color=grey-7")


def render_log_card(log_entries):
    if not log_entries:
        return
    with ui.card().classes("w-full"):
        render_log(log_entries)


def render_refinement_box(context, prev_text, on_refine, extra_button=None):
    """on_refine: async callable, gọi sau khi đã ghép góp ý vào context.user_query.

    Tách ra module-level (context truyền tường minh thay vì closure) để trang chatbot
    (`views/chat_experiment.py`) tái dùng được đúng logic này, không phải viết lại.
    """
    if context.experiment_type in _EXPLANATION_ONLY_TYPES:
        return
    with ui.card().classes("w-full mt-1"):
        _card_header("refresh", "#EE0033", "Chưa hài lòng với kết quả?", "Góp ý hoặc yêu cầu chạy lại theo hướng khác")
        feedback = ui.textarea("Để trống nếu không cần chạy lại").classes("w-full")

        async def run_refine():
            if not feedback.value or not feedback.value.strip():
                ui.notify("Hãy nhập góp ý trước khi chạy lại.", color="negative")
                return
            combined_prev = (prev_text or "")[:MAX_FEEDBACK_CONTEXT_CHARS]
            context.user_query = (
                f"{context.user_query or ''}\n\n"
                f"--- Kết quả lần chạy trước ---\n{combined_prev}\n\n"
                f"--- Góp ý của người dùng cho lần chạy này ---\n{feedback.value.strip()}\n"
                "Hãy điều chỉnh phân tích theo góp ý này, đừng lặp lại y nguyên kết quả cũ."
            ).strip()
            await on_refine()

        with ui.row().classes("gap-2 mt-2"):
            ui.button("Chạy lại với góp ý này", icon="play_arrow", on_click=run_refine, color="primary")
            if extra_button:
                extra_button()


def _render_summary_card(kind, summary_text):
    if not summary_text:
        return
    icon, color, title, subtitle = _SUMMARY_CARD_META.get(kind, ("auto_awesome", "#EE0033", "Tóm tắt", ""))
    with ui.card().classes("w-full"):
        _card_header(icon, color, title, subtitle)
        info_box(lambda: safe_markdown(summary_text))


def _render_eda_sections(result):
    results_data = (result.data or {}).get("results", {})
    missing = results_data.get("check_missing") or {}
    n_rows = missing.get("n_rows")
    n_cols = len(missing.get("columns", {})) if missing.get("columns") else None
    total_missing = missing.get("total_missing")
    missing_pct = None
    if n_rows and n_cols:
        missing_pct = total_missing / (n_rows * n_cols) * 100

    outlier_total = 0
    found_outlier = False
    for key in ("check_outliers_iqr", "check_outliers_rolling"):
        # results_for_tool: gộp cả các lần gọi lại tool này cho cột khác (key riêng theo
        # _disambiguated_key) — không chỉ đọc lần gọi đầu, tránh thiếu outlier của cột khác.
        for info in results_for_tool(results_data, key):
            if isinstance(info, dict) and "n_outliers" in info:
                outlier_total += info["n_outliers"]
                found_outlier = True

    max_corr = None
    for key in ("correlation_matrix", "spearman_correlation"):
        pairs = significant_pairs_for_tool(results_data, key)
        if pairs:
            candidate = max(abs(p["r"]) for p in pairs)
            max_corr = candidate if max_corr is None else max(max_corr, candidate)

    with ui.row().classes("w-full gap-3"):
        stat_card(
            "error_outline",
            "Missing values",
            f"{missing_pct:.1f}%" if missing_pct is not None else "—",
            color="#EE0033",
        )
        stat_card("scatter_plot", "Outlier phát hiện", outlier_total if found_outlier else "—", color="#854F0B")
        stat_card("link", "Tương quan cao nhất", f"{max_corr:.2f}" if max_corr is not None else "—", color="#2E7D32")

    if n_rows is not None and n_cols is not None:
        with ui.card().classes("w-full"):
            _card_header("table_chart", "#185FA5", "Tổng quan dữ liệu", "Sau khi merge & kiểm tra chất lượng")
            with ui.row().classes("w-full gap-8"):
                with ui.column().classes("gap-0"):
                    ui.label("Tổng dòng").classes("text-xs text-gray-400")
                    ui.label(f"{n_rows:,}").classes("text-lg font-medium")
                with ui.column().classes("gap-0"):
                    ui.label("Số cột").classes("text-xs text-gray-400")
                    ui.label(str(n_cols)).classes("text-lg font-medium")
                if missing.get("cols_with_missing"):
                    with ui.column().classes("gap-0"):
                        ui.label("Cột có missing").classes("text-xs text-gray-400")
                        ui.label(str(len(missing["cols_with_missing"]))).classes("text-lg font-medium")


def _render_preprocessing_sections(result):
    steps_list = (result.data or {}).get("steps") or []
    if not steps_list:
        return
    with ui.card().classes("w-full"):
        _card_header(
            "fact_check", "#2E7D32", "Tóm tắt các bước đã xử lý", "Agent tự quyết định dựa trên kết quả kiểm tra"
        )
        with ui.column().classes("w-full gap-2"):
            for step_text in steps_list:
                with ui.row().classes("items-start gap-2 p-2 w-full").style("background:#eaf3de; border-radius:7px;"):
                    ui.icon("check", color="#2E7D32").style("font-size:16px; margin-top:1px;")
                    ui.label(step_text).classes("text-sm").style("color:#1a1a1a;")


def _render_training_sections(result):
    data = result.data or {}
    leaderboard = data.get("leaderboard") or []
    best_name = data.get("best_model")
    metric = data.get("metric")

    best_row = next((r for r in leaderboard if r.get("model") == best_name), leaderboard[0] if leaderboard else {})

    with ui.row().classes("w-full gap-3"):
        stat_card("emoji_events", "Best model", best_name or "—", color="#2E7D32")
        for key, value in best_row.items():
            if key == "model":
                continue
            stat_card("show_chart", _METRIC_LABELS.get(key, key.upper()), _format_metric(value), color="#854F0B")

    if leaderboard:
        higher_better = metric in HIGHER_IS_BETTER_METRICS
        ordered = sorted(leaderboard, key=lambda r: (r.get(metric) is None, r.get(metric, 0)), reverse=higher_better)
        metric_cols = [c for c in ordered[0].keys() if c != "model"]
        with ui.card().classes("w-full"):
            _card_header("table_chart", "#854F0B", "Leaderboard", f"So sánh {len(ordered)} model")
            with ui.column().classes("w-full gap-1"):
                with ui.row().classes("w-full items-center gap-2 px-2 py-1").style(
                    "background:#F7F7F8; border-radius:6px;"
                ):
                    ui.label("").style("width:22px;")
                    ui.label("Model").classes("flex-1 text-xs font-medium").style("color:#44494D;")
                    for col in metric_cols:
                        ui.label(_METRIC_LABELS.get(col, col.upper())).classes("text-xs font-medium").style(
                            "width:90px; text-align:right; color:#44494D;"
                        )
                for i, row in enumerate(ordered):
                    is_best = i == 0
                    with ui.row().classes("w-full items-center gap-2 px-2 py-1").style(
                        f"border-radius:6px; {'background:#fff8f0;' if is_best else ''}"
                    ):
                        if is_best:
                            ui.label("1").style(
                                "background:#EE0033; color:#fff; border-radius:4px; padding:0 6px; "
                                "font-size:10px; width:22px; text-align:center;"
                            )
                        else:
                            ui.label(str(i + 1)).classes("text-xs text-gray-400").style(
                                "width:22px; text-align:center;"
                            )
                        ui.label(row.get("model", "")).classes(
                            "flex-1 text-sm" + (" font-medium" if is_best else "")
                        )
                        for col in metric_cols:
                            ui.label(_format_metric(row.get(col))).classes("text-sm").style(
                                "width:90px; text-align:right;"
                            )


def _render_evaluation_sections(result):
    metrics = (result.data or {}).get("metrics") or {}
    numeric_metrics = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
    if numeric_metrics:
        with ui.row().classes("w-full gap-3"):
            for key, value in numeric_metrics.items():
                stat_card("show_chart", _METRIC_LABELS.get(key, key.upper()), _format_metric(value), color="#185FA5")
    elif metrics.get("note"):
        info_box(lambda: ui.label(metrics["note"]).classes("text-sm text-gray-700"))


def _render_inference_sections(result, context):
    data = result.data or {}
    output_path = data.get("output_path")
    n_rows = None
    avg_pred = None
    if output_path and os.path.exists(output_path):
        try:
            df_out = pd.read_csv(output_path)
            n_rows = len(df_out)
            if "predicted" in df_out.columns and pd.api.types.is_numeric_dtype(df_out["predicted"]):
                avg_pred = df_out["predicted"].mean()
        except Exception:
            pass

    model_name = None
    model_path = context.extra.get("model_path")
    if model_path:
        model_name = os.path.splitext(os.path.basename(model_path))[0]

    with ui.row().classes("w-full gap-3"):
        stat_card(
            "format_list_numbered", "Số dòng dự đoán", f"{n_rows:,}" if n_rows is not None else "—", color="#185FA5"
        )
        stat_card("smart_toy", "Model dùng", model_name or "—", color="#2E7D32")
        stat_card(
            "show_chart", "Dự báo trung bình", f"{avg_pred:,.1f}" if avg_pred is not None else "—", color="#854F0B"
        )

    bonus = data.get("bonus_metrics")
    if bonus:
        numeric_bonus = {k: v for k, v in bonus.items() if isinstance(v, (int, float))}
        if numeric_bonus:
            with ui.card().classes("w-full"):
                _card_header("fact_check", "#185FA5", "Metrics bổ sung", "Tính từ cột target có sẵn trong file mới")
                with ui.row().classes("w-full gap-8"):
                    for key, value in numeric_bonus.items():
                        with ui.column().classes("gap-0"):
                            ui.label(_METRIC_LABELS.get(key, key.upper())).classes("text-xs text-gray-400")
                            ui.label(_format_metric(value)).classes("text-lg font-medium")


def _render_kind_sections(kind, result, context):
    if kind == "eda":
        _render_eda_sections(result)
    elif kind == "preprocessing":
        _render_preprocessing_sections(result)
    elif kind == "training":
        _render_training_sections(result)
    elif kind == "evaluation":
        _render_evaluation_sections(result)
    elif kind == "inference":
        _render_inference_sections(result, context)


def _render_data_preview(kind, result):
    if kind == "preprocessing":
        processed_path = (result.data or {}).get("processed_path")
        if processed_path and os.path.exists(processed_path):
            with ui.card().classes("w-full"):
                _card_header("table_chart", "#5F5E5A", "Preview dữ liệu sau xử lý", "5 dòng đầu")
                _df_table(pd.read_csv(processed_path))
    elif kind == "inference":
        output_path = (result.data or {}).get("output_path")
        if output_path and os.path.exists(output_path):
            with ui.card().classes("w-full"):
                _card_header(
                    "table_chart", "#5F5E5A", "Kết quả dự đoán (5 dòng đầu)", "Cột 'predicted' thêm vào file gốc"
                )
                _df_table(pd.read_csv(output_path))


def render_result_body(result, kind, context):
    if not result.success:
        with ui.card().classes("w-full").style("border-left:3px solid #C62828;"):
            ui.label(f"Lỗi: {result.error}").classes("text-red-700 text-sm")
        return

    _render_summary_card(kind, result.summary)
    _render_kind_sections(kind, result, context)
    _render_data_preview(kind, result)

    trigger_charts, planner_charts = _split_charts_by_source(result.charts)
    if trigger_charts:
        with ui.card().classes("w-full"):
            _card_header(
                "bar_chart", "#5F5E5A", "Biểu đồ tổng quan dữ liệu", "Missing pattern · Cột lệch nhất · Đa biến (pairplot)"
            )
            render_charts(trigger_charts)

    if result.insights:
        with ui.card().classes("w-full"):
            _card_header("auto_awesome", "#EE0033", "Insight phân tích", "Tổng hợp từ EDA Agent · có biểu đồ minh họa")
            has_linkable = any(c.get("id") is not None for c in planner_charts)
            if has_linkable:
                render_insight_with_charts(result.insights, planner_charts)
            else:
                safe_markdown(result.insights)
                if planner_charts:
                    render_charts(planner_charts)
    elif planner_charts:
        with ui.card().classes("w-full"):
            _card_header("bar_chart", "#185FA5", "Biểu đồ", "")
            render_charts(planner_charts)

    render_code_export(kind, result, context)
    render_log_card(result.log)


def _extract_artifact_paths(context, result):
    """Lấy các path file đã sinh ra (model/CSV/báo cáo) để run_history.py có thể cho tải lại —
    file vẫn còn trên đĩa sau khi process restart, chỉ cần nhớ đúng path."""
    data = result.data or {}
    if context.experiment_type == "Full Pipeline":
        steps = data.get("steps", {})
        preprocessing = steps.get("preprocessing")
        training = steps.get("training")
        return {
            "report_path": data.get("report_path"),
            "processed_path": (preprocessing.data or {}).get("processed_path")
            if preprocessing and preprocessing.success
            else None,
            "model_path": (training.data or {}).get("model_path") if training and training.success else None,
            "output_path": None,
        }
    return {
        "report_path": data.get("report_path"),
        "processed_path": data.get("processed_path"),
        "model_path": data.get("model_path"),
        "output_path": data.get("output_path"),
    }


def _save_run(context, result, start_time=None, source="form", initial_description=None):
    """start_time: datetime lúc bắt đầu chạy (trước lời gọi agent chặn) — dùng để tính thời
    gian chạy THẬT. Không thể suy ra từ ExecutionLogger vì log chỉ ghi các bước tool đồng bộ
    (vài ms), không ghi các lời gọi LLM (thường chiếm phần lớn thời gian chạy).

    source/initial_description: phân biệt run tạo qua wizard ("form", mặc định) hay qua
    `/chat` ("chat") — xem CHATBOT_FEATURE.md mục "Khuất mắc nhỏ #1b". run_history.py dùng
    `source` để hiện badge "Qua chatbot"."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = ExecutionLogger(run_id)
    for entry in result.log:
        logger.log(entry.get("step"), entry, entry.get("status"))
    logger.save()

    # Full Pipeline ghi đè context.files qua từng stage (vd "processed" sau bước xử lý dữ
    # liệu) — pipeline_agent.py đã tự lưu tên file gốc vào context.extra["original_files"]
    # ngay đầu run_stage() cho đúng mục đích này, ưu tiên đọc từ đó trước khi fallback.
    file_names = context.extra.get("original_files") or list(context.files.keys())

    runs = state.get("runs", [])
    runs.append(
        {
            "run_id": run_id,
            "problem": context.problem_name,
            "experiment_type": context.experiment_type,
            "status": "success" if result.success else "error",
            "summary": result.summary,
            "error": result.error,
            "n_files": len(file_names),
            "file_names": file_names,
            "user_query": context.user_query,
            "duration_seconds": (datetime.now() - start_time).total_seconds() if start_time else None,
            "source": source,
            "initial_description": initial_description,
            **_extract_artifact_paths(context, result),
        }
    )
    state.set_value("runs", runs)
    return run_id


@ui.page("/run-experiment")
async def run_experiment_page():
    theme.apply()
    state.ensure_defaults()
    ui.add_css(_TABLE_CSS)
    render_header()

    context = state.get_object(state.get("context_key"))
    if context is None:
        render_breadcrumbs([("Trang chủ", "/"), ("Cấu hình", "/experiment-config"), ("Chạy experiment", None)])
        with ui.column().classes("w-full gap-2").style("background:#F7F7F8; min-height:100vh; padding:24px 32px;"):
            ui.label("Vui lòng cấu hình experiment trước.").classes("text-orange-600")
            ui.button("Quay lại", on_click=lambda: ui.navigate.to("/experiment-config"))
        return

    crumb_zone = ui.column().classes("w-full gap-0")
    body = ui.column().classes("w-full gap-3").style("background:#F7F7F8; min-height:100vh; padding:24px 32px;")

    def _phase_label():
        if not state.get("input_confirmed"):
            return "Xác nhận & Chạy"
        if context.experiment_type == "Tùy chỉnh":
            return "Kết quả" if state.get("custom_response") is not None else "Đang chạy"
        if context.experiment_type == "Full Pipeline":
            return "Kết quả" if state.get_object(state.get("pipeline_result_key")) is not None else "Đang chạy"
        return "Kết quả" if state.get_object(state.get("agent_result_key")) is not None else "Đang chạy"

    async def rerun():
        crumb_zone.clear()
        body.clear()
        with crumb_zone:
            render_breadcrumbs(
                [("Trang chủ", "/"), ("Cấu hình", "/experiment-config"), (_phase_label(), None)]
            )
        with body:
            await render_body()

    def reset_pipeline_state():
        state.set_value("pipeline_steps_key", None)
        state.set_value("pipeline_stage_idx", 0)
        state.set_value("pipeline_result_key", None)
        state.set_value("pipeline_start_time", None)
        state.set_value("agent_result_key", None)
        state.set_value("custom_response", None)
        state.set_value("detection_key", None)
        state.set_value("merge_decision", None)
        state.set_value("input_confirmed", False)

    def render_input_summary(on_confirmed):
        """on_confirmed: async callable, gọi khi user bấm 'Xác nhận & Chạy'."""

        async def back_to_config():
            reset_pipeline_state()
            ui.navigate.to("/experiment-config")

        _header_row(
            context,
            "Xác nhận trước khi chạy",
            right=lambda: ui.button(
                "Chỉnh lại cấu hình", icon="settings", on_click=back_to_config
            ).props("outline color=grey-7"),
        )

        with ui.row().classes("w-full gap-3 mt-2 items-stretch no-wrap"):
            with ui.card().classes("flex-1"):
                _card_header("description", "#EE0033", "File dữ liệu", f"{len(context.files)} file đã chọn")
                with ui.column().classes("w-full gap-2"):
                    for name, df in context.files.items():
                        with ui.row().classes("w-full items-center gap-2 p-2").style(
                            "background:#F7F7F8; border-radius:6px; border:0.5px solid rgba(0,0,0,0.08);"
                        ):
                            ui.icon("description", color="#EE0033").style("font-size:16px;")
                            with ui.column().classes("gap-0"):
                                ui.label(name).classes("text-sm font-medium")
                                ui.label(f"{len(df):,} dòng × {len(df.columns)} cột").classes(
                                    "text-xs text-gray-400"
                                )

            with ui.card().classes("flex-1"):
                _card_header("chat_bubble", "#757575", "Yêu cầu phân tích", "Từ người dùng")
                info_box(lambda: ui.label(context.user_query or "(không có)").classes("text-sm text-gray-700"))
                if context.domain_context:
                    domain_note = context.domain_name if context.domain_name else "File nghiệp vụ đã upload"
                    ui.label(f"Nghiệp vụ: {domain_note}").classes("text-xs text-gray-400 mt-2")
                else:
                    ui.label("Không có file nghiệp vụ — agent tự phân tích chung").classes(
                        "text-xs text-gray-400 mt-2"
                    )

        with ui.card().classes("w-full mt-1"):
            _card_header("table_chart", "#1976D2", "Xem trước dữ liệu", "5 dòng đầu mỗi file")
            for name, df in context.files.items():
                ui.label(name).classes("text-xs font-medium text-gray-600 mt-1")
                _df_table(df)

        q1_widget = None
        q2_widget = None
        if _detect_ambiguity(context.user_query):
            with ui.card().classes("w-full mt-1").style("background:#FFF8F0; border:0.5px solid rgba(133,79,11,0.2);"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("warning_amber", color="#854F0B").style("font-size:18px;")
                    ui.label("Yêu cầu chưa rõ ràng — làm rõ thêm để kết quả tốt hơn").classes(
                        "text-sm font-medium"
                    ).style("color:#854F0B;")
                q1_widget = ui.input("Bạn muốn tập trung vào cột nào? (để trống = phân tích tất cả)").classes(
                    "w-full mt-2"
                )
                q2_widget = ui.input(
                    "Muốn phân tích gì? (phân phối / tương quan / xu hướng thời gian / ...)"
                ).classes("w-full")

        async def confirm():
            extra = " ".join(
                filter(
                    None,
                    [
                        (q1_widget.value or "").strip() if q1_widget else "",
                        (q2_widget.value or "").strip() if q2_widget else "",
                    ],
                )
            )
            if extra:
                context.user_query = f"{context.user_query or ''} {extra}".strip()
            await on_confirmed()

        with ui.row().classes("mt-3 gap-2"):
            ui.button("Xác nhận & Chạy", icon="play_arrow", on_click=confirm, color="primary")
            ui.button("Chỉnh lại cấu hình", on_click=back_to_config).props("flat")

    def render_stage_refinement_box(stage, prev_text, steps, on_refine):
        if stage in _EXPLANATION_ONLY_STAGES:
            return
        with ui.card().classes("w-full mt-1"):
            _card_header(
                "refresh", "#EE0033", f"Chưa hài lòng với bước {STAGE_LABELS[stage]}?", "Góp ý cho riêng bước này"
            )
            feedback = ui.textarea("Để trống nếu không cần chạy lại bước này").classes("w-full")

            async def run_refine():
                if not feedback.value or not feedback.value.strip():
                    ui.notify("Hãy nhập góp ý trước khi chạy lại.", color="negative")
                    return
                combined_prev = (prev_text or "")[:MAX_FEEDBACK_CONTEXT_CHARS]
                context.user_query = (
                    f"{context.user_query or ''}\n\n"
                    f"--- Kết quả bước {STAGE_LABELS[stage]} lần trước ---\n{combined_prev}\n\n"
                    f"--- Góp ý của người dùng cho bước này ---\n{feedback.value.strip()}\n"
                    "Hãy điều chỉnh theo góp ý này, đừng lặp lại y nguyên kết quả cũ."
                ).strip()
                refined = state.get("stage_just_refined", {})
                refined[stage] = True
                state.set_value("stage_just_refined", refined)
                del steps[stage]
                await on_refine()

            ui.button("Chạy lại bước này với góp ý", icon="play_arrow", on_click=run_refine, color="primary").classes(
                "mt-2"
            )

    async def go_back():
        reset_pipeline_state()
        state.set_value("context_key", None)
        ui.navigate.to("/select-experiment")

    def render_nav_buttons():
        with ui.row().classes("mt-1"):
            ui.button("Quay lại", on_click=go_back).props("outline color=grey-7")

    def render_final_report(result):
        _header_row(
            context,
            "Kết quả tổng hợp Pipeline",
            badge_text="Thành công" if result.success else "Lỗi",
            right=_result_header_actions(context, result, go_back),
        )

        if result.charts:
            with ui.card().classes("w-full"):
                _card_header("bar_chart", "#185FA5", "Tất cả biểu đồ", f"{len(result.charts)} biểu đồ từ các bước")
                render_charts(result.charts)

        render_log_card(result.log)

        steps = result.data.get("steps", {})
        with ui.row().classes("gap-2"):
            preprocessing_step = steps.get("preprocessing")
            if preprocessing_step and preprocessing_step.success:
                processed_path = preprocessing_step.data.get("processed_path")
                if processed_path and os.path.exists(processed_path):
                    with open(processed_path, "rb") as f:
                        data = f.read()
                    ui.button(
                        "Tải dữ liệu đã xử lý (CSV)",
                        icon="download",
                        on_click=lambda d=data: ui.download(d, filename=os.path.basename(processed_path)),
                    ).props("outline color=grey-7")

            training_step = steps.get("training")
            if training_step and training_step.success:
                model_path = training_step.data.get("model_path")
                if model_path and os.path.exists(model_path):
                    with open(model_path, "rb") as f:
                        data = f.read()
                    ui.button(
                        "Tải model về",
                        icon="download",
                        on_click=lambda d=data: ui.download(d, filename=os.path.basename(model_path)),
                    ).props("outline color=grey-7")

        if result.success:
            parts = []
            for stage, r in steps.items():
                if r.summary:
                    parts.append(f"[{STAGE_LABELS.get(stage, stage)}] {r.summary}")
            combined_text = "\n".join(parts)

            async def on_refine():
                state.set_value("pipeline_steps_key", None)
                state.set_value("pipeline_stage_idx", 0)
                state.set_value("pipeline_result_key", None)
                await rerun()

            render_refinement_box(context, combined_text, on_refine)

        render_nav_buttons()

    def _pipeline_start_time():
        """Ghi lại mốc bắt đầu pipeline 1 lần duy nhất vào state — render_pipeline() được gọi
        lại nhiều lần (mỗi rerun() sau mỗi stage) nên không thể dùng biến local."""
        iso = state.get("pipeline_start_time")
        if iso is None:
            iso = datetime.now().isoformat()
            state.set_value("pipeline_start_time", iso)
        return datetime.fromisoformat(iso)

    async def render_pipeline():
        agent = PipelineAgent(context)
        steps = state.get_object(state.get("pipeline_steps_key"))
        if steps is None:
            steps = {}
            state.set_value("pipeline_steps_key", state.put_object(steps))
        stage_idx = state.get("pipeline_stage_idx", 0)

        pipeline_result = state.get_object(state.get("pipeline_result_key"))
        if pipeline_result is None:
            _header_row(context, "Pipeline đang chạy theo từng bước")

        for stage in STAGES[:stage_idx]:
            result = steps.get(stage)
            if result:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check_circle", color="#2E7D32").style("font-size:16px;")
                    ui.label(STAGE_LABELS[stage]).classes("text-sm font-medium")
                render_result_body(result, stage, context)

        if pipeline_result is not None:
            render_final_report(pipeline_result)
            return

        if stage_idx >= len(STAGES):
            _simple_loading_card("Đang tổng hợp báo cáo cuối cùng...")
            final = await nicegui_run.io_bound(agent.finalize, context, steps)
            state.set_value("pipeline_result_key", state.put_object(final))
            _save_run(context, final, _pipeline_start_time())
            await rerun()
            return

        stage = STAGES[stage_idx]

        if stage not in steps:
            _pipeline_start_time()
            timer = _pipeline_running_card(steps, stage_idx)
            await nicegui_run.io_bound(lambda: asyncio.run(agent.run_stage(stage, context, steps)))
            timer.cancel()
            await rerun()
            return

        result = steps[stage]
        refined = state.get("stage_just_refined", {})
        if refined.pop(stage, False):
            state.set_value("stage_just_refined", refined)
            ui.notify(f"Đã chạy lại bước {STAGE_LABELS[stage]} với góp ý mới.", type="positive")

        ui.label(STAGE_LABELS[stage]).classes("text-sm font-medium")
        render_result_body(result, stage, context)

        if not result.success:
            ui.label(f"Lỗi ở bước {STAGE_LABELS[stage]}: {result.error}").classes("text-red-600")
            _simple_loading_card("Đang tổng hợp báo cáo cuối cùng...")
            final = await nicegui_run.io_bound(agent.finalize, context, steps)
            state.set_value("pipeline_result_key", state.put_object(final))
            _save_run(context, final, _pipeline_start_time())
            await rerun()
            return

        stage_prev_text = "\n\n".join(filter(None, [
            result.summary if isinstance(result.summary, str) else "",
            result.insights if isinstance(result.insights, str) else "",
        ]))
        render_stage_refinement_box(stage, stage_prev_text, steps, rerun)

        async def continue_stage():
            state.set_value("pipeline_stage_idx", stage_idx + 1)
            await rerun()

        async def stop_here():
            _simple_loading_card("Đang tổng hợp báo cáo cuối cùng...")
            final = await nicegui_run.io_bound(agent.finalize, context, steps)
            state.set_value("pipeline_result_key", state.put_object(final))
            _save_run(context, final, _pipeline_start_time())
            await rerun()

        with ui.row().classes("mt-2 gap-2"):
            ui.button("Tiếp tục", icon="arrow_forward", on_click=continue_stage, color="primary")
            ui.button("Dừng tại đây — xem báo cáo", on_click=stop_here).props("outline color=grey-7")

    async def run_single_agent():
        _header_row(context, "Agent đang xử lý")
        timer = _agent_running_card(context.experiment_type)
        start_time = datetime.now()
        agent = route(context.experiment_type, context)
        result = await nicegui_run.io_bound(lambda: asyncio.run(agent.run(context)))
        timer.cancel()
        state.set_value("agent_result_key", state.put_object(result))

        if result.success and context.experiment_type == "Khám phá dữ liệu":
            try:
                report_path = await nicegui_run.io_bound(
                    report_generator.generate,
                    dataset_info={
                        "files": list(context.files.keys()),
                        "problem_name": context.problem_name,
                        "experiment_type": context.experiment_type,
                    },
                    eda_results=result.data.get("results", {}),
                    ml_results=None,
                    execution_log=result.log,
                    charts=result.charts,
                )
                result.data["report_path"] = report_path
            except Exception as e:
                result.log.append({"step": "report_generator", "status": "error", "error": str(e)})

        # Lưu run SAU khi report_path (nếu có) đã được ghi vào result.data — lưu trước đó sẽ
        # luôn mất report_path vì _extract_artifact_paths đọc result.data tại đúng lúc gọi.
        _save_run(context, result, start_time)
        await rerun()

    def render_single_result(result):
        kind = EXPERIMENT_TYPE_TO_KIND.get(context.experiment_type)
        _header_row(
            context,
            "Kết quả phân tích",
            badge_text="Thành công" if result.success else "Lỗi",
            right=_result_header_actions(context, result, go_back),
        )
        render_result_body(result, kind, context)

        if not result.success:
            render_nav_buttons()
            return

        prev_text = "\n\n".join(filter(None, [
            result.summary if isinstance(result.summary, str) else "",
            result.insights if isinstance(result.insights, str) else "",
        ]))

        async def on_refine():
            state.set_value("agent_result_key", None)
            await rerun()

        def _csv_download_button(d, p):
            ui.button(
                "Tải CSV kết quả",
                icon="download",
                on_click=lambda: ui.download(d, filename=os.path.basename(p)),
            ).props("outline color=grey-7")

        extra_button = None
        if kind == "inference":
            output_path = (result.data or {}).get("output_path")
            if output_path and os.path.exists(output_path):
                with open(output_path, "rb") as f:
                    data = f.read()
                extra_button = lambda d=data, p=output_path: _csv_download_button(d, p)

        render_refinement_box(context, prev_text, on_refine, extra_button=extra_button)
        render_nav_buttons()

    async def render_body():
        # Tùy chỉnh — không có agent, gọi LLM trực tiếp với câu hỏi của user
        if context.experiment_type == "Tùy chỉnh":
            if not state.get("input_confirmed"):
                async def confirm_custom():
                    state.set_value("input_confirmed", True)
                    await rerun()

                render_input_summary(confirm_custom)
                return

            custom_response = state.get("custom_response")
            if custom_response is None:
                _header_row(context, "Agent đang xử lý")
                timer = _agent_running_card(context.experiment_type)
                response = await nicegui_run.io_bound(call_llm, context.user_query, model=MODEL_DEFAULT)
                timer.cancel()
                state.set_value("custom_response", response)
                await rerun()
                return

            _header_row(context, "Kết quả", badge_text="Thành công")
            with ui.card().classes("w-full"):
                safe_markdown(custom_response)

            async def go_back_custom():
                reset_pipeline_state()
                ui.navigate.to("/select-experiment")

            ui.button("Quay lại", on_click=go_back_custom).props("outline color=grey-7")
            return

        # Khám phá dữ liệu / Full Pipeline + nhiều file -> hỏi merge trước
        if context.experiment_type in ("Khám phá dữ liệu", "Full Pipeline") and len(context.files) > 1:
            detection = state.get_object(state.get("detection_key"))
            if detection is None:
                from agents.file_detector import detect

                _header_row(context, "Đang chuẩn bị dữ liệu")
                _simple_loading_card("Đang phân tích schema các file...")
                detection = await nicegui_run.io_bound(detect, context.files, context.file_paths)
                state.set_value("detection_key", state.put_object(detection))
                await rerun()
                return

            merge_plan = detection["merge_plan"]
            if merge_plan.can_merge and state.get("merge_decision") is None:
                async def choose_merge():
                    state.set_value("merge_decision", "merge")
                    context.extra["merge_confirmed"] = True
                    await rerun()

                async def choose_separate():
                    state.set_value("merge_decision", "separate")
                    context.extra["merge_confirmed"] = False
                    await rerun()

                _header_row(context, "Đề xuất kết hợp file")
                with ui.card().classes("w-full mt-1"):
                    _card_header("call_merge", "#1976D2", "Đề xuất kết hợp file", "Dựa trên schema phát hiện được")
                    if detection.get("suggestion"):
                        safe_markdown(detection["suggestion"])
                    ui.label(merge_plan.reason).classes("text-sm text-gray-600 mt-1")
                    with ui.row().classes("mt-3 gap-2"):
                        ui.button("Đồng ý kết hợp", icon="check", on_click=choose_merge, color="primary")
                        ui.button("Phân tích riêng từng file", on_click=choose_separate).props(
                            "outline color=grey-7"
                        )
                return

        if not state.get("input_confirmed"):
            async def confirm_main():
                state.set_value("input_confirmed", True)
                await rerun()

            render_input_summary(confirm_main)
            return

        if context.experiment_type == "Full Pipeline":
            await render_pipeline()
            return

        agent_result = state.get_object(state.get("agent_result_key"))
        if agent_result is None:
            await run_single_agent()
            return

        render_single_result(agent_result)

    with crumb_zone:
        render_breadcrumbs([("Trang chủ", "/"), ("Cấu hình", "/experiment-config"), (_phase_label(), None)])
    with body:
        await render_body()
