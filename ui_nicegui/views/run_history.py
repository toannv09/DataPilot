"""Lịch sử các lần chạy + log chi tiết. Tương đương ui/views/run_history.py.

Khác bản cũ (1 cột ui.expansion + table thô): trang này filter/expand bằng cách rebuild lại
1 container cục bộ (`list_zone`) — không dùng pattern "clear() + rebuild toàn page" như
run_experiment.py vì ở đây không có flow async nhiều bước, chỉ là 1 trang list tĩnh có filter
phía client (lọc trên list đã có sẵn trong `state`, không gọi lại agent).
"""

import os
from datetime import datetime

from nicegui import ui

import state
import theme
from components.header import render_breadcrumbs, render_chip, render_header
from components.result_widgets import info_box, safe_markdown, stat_card
from mlops.logger import ExecutionLogger

EXPERIMENT_TYPES = [
    "Tất cả experiment",
    "Khám phá dữ liệu",
    "Xử lý dữ liệu",
    "Huấn luyện mô hình",
    "Đánh giá mô hình",
    "Suy luận mô hình",
    "Full Pipeline",
]

EXPERIMENT_CHIP_COLOR = {
    "Khám phá dữ liệu": "#44494D",
    "Xử lý dữ liệu": "#185FA5",
    "Huấn luyện mô hình": "#854F0B",
    "Đánh giá mô hình": "#2E7D32",
    "Suy luận mô hình": "#5F5E5A",
    "Full Pipeline": "#44494D",
}

STATUS_DOT = {"success": "#3B6D11", "error": "#EE0033"}

_ARTIFACT_BUTTONS = {
    "report_path": ("Xem báo cáo", "description"),
    "processed_path": ("Tải CSV đã xử lý", "table_chart"),
    "model_path": ("Tải model (.pkl)", "smart_toy"),
    "output_path": ("Tải kết quả dự đoán (CSV)", "download"),
}


def _parse_run_time(run_id):
    try:
        return datetime.strptime(run_id, "%Y%m%d_%H%M%S")
    except (ValueError, TypeError):
        return None


def _format_duration(seconds):
    if seconds is None:
        return None
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


def _open_report(run, report_path):
    state.set_value("report_path", report_path)
    state.set_value(
        "report_meta",
        {
            "problem": run.get("problem"),
            "experiment_type": run.get("experiment_type"),
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "duration_seconds": run.get("duration_seconds"),
        },
    )
    state.set_value("report_return_path", "/run-history")
    state.set_value("report_breadcrumbs", [("Lịch sử chạy", "/run-history")])
    ui.navigate.to("/report")


def _matches_filters(run, filters):
    if filters["status"] == "Thành công" and run.get("status") != "success":
        return False
    if filters["status"] == "Thất bại" and run.get("status") != "error":
        return False
    if filters["exp_type"] != "Tất cả experiment" and run.get("experiment_type") != filters["exp_type"]:
        return False
    q = (filters["q"] or "").strip().lower()
    if q and q not in run.get("run_id", "").lower() and q not in run.get("problem", "").lower():
        return False
    return True


@ui.page("/run-history")
def run_history_page():
    theme.apply()
    state.ensure_defaults()

    render_header()
    render_breadcrumbs([("Lịch sử chạy", None)])

    filters = {"q": "", "exp_type": "Tất cả experiment", "status": "Tất cả"}
    expanded_ids = set()

    with ui.column().classes("w-full gap-3").style("background:#F7F7F8; min-height:100vh; padding:24px 32px;"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Lịch sử chạy").classes("text-base font-medium").style("color:#1a1a1a;")
                ui.label("Toàn bộ các lần thực thi experiment · mới nhất trước").classes(
                    "text-xs text-gray-400"
                )

        stats_zone = ui.row().classes("w-full gap-3")

        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            search_input = ui.input(placeholder="Tìm theo run_id, bài toán...").props("outlined dense clearable").classes(
                "flex-1"
            ).style("min-width:220px;")
            exp_select = ui.select(EXPERIMENT_TYPES, value="Tất cả experiment").props("outlined dense").style(
                "min-width:190px;"
            )

            tab_buttons = {}

            def make_tab(label):
                def select_tab():
                    filters["status"] = label
                    for lbl, btn in tab_buttons.items():
                        if lbl == label:
                            btn.props(remove="flat color=grey-7", add="unelevated color=primary text-color=white")
                        else:
                            btn.props(remove="unelevated color=primary text-color=white", add="flat color=grey-7")
                    render_list()

                return select_tab

            with ui.row().classes("gap-1 p-1").style(
                "background:#fff; border:0.5px solid rgba(0,0,0,0.1); border-radius:7px;"
            ):
                for label in ("Tất cả", "Thành công", "Thất bại"):
                    btn = ui.button(label, on_click=make_tab(label)).props("flat dense color=grey-7").classes(
                        "text-xs"
                    )
                    tab_buttons[label] = btn
            tab_buttons["Tất cả"].props(remove="flat color=grey-7", add="unelevated color=primary text-color=white")

        list_zone = ui.column().classes("w-full gap-2")

        def render_stats():
            stats_zone.clear()
            runs = state.get("runs", [])
            total = len(runs)
            n_success = sum(1 for r in runs if r.get("status") == "success")
            n_failed = sum(1 for r in runs if r.get("status") == "error")
            durations = [r["duration_seconds"] for r in runs if r.get("duration_seconds") is not None]
            avg_duration = sum(durations) / len(durations) if durations else None
            with stats_zone:
                stat_card("play_arrow", "Tổng lần chạy", total, color="#5F5E5A")
                stat_card("check_circle", "Thành công", n_success, color="#2E7D32")
                stat_card("cancel", "Thất bại", n_failed, color="#EE0033")
                stat_card(
                    "schedule", "Thời gian TB", _format_duration(avg_duration) or "—", color="#854F0B"
                )

        def delete_run(run):
            state.delete_run_record(run.get("run_id"))
            ui.notify(f"Đã xoá {run['run_id']}", color="positive")
            render_stats()
            render_list()

        def view_run(run):
            report_path = run.get("report_path")
            if report_path and os.path.exists(report_path):
                _open_report(run, report_path)
                return
            expanded_ids.add(run["run_id"])
            render_list()

        def toggle(run_id):
            if run_id in expanded_ids:
                expanded_ids.discard(run_id)
            else:
                expanded_ids.add(run_id)
            render_list()

        def render_detail(run):
            with ui.column().classes("w-full gap-3 p-4").style(
                "background:#fafafa; border-top:0.5px solid rgba(0,0,0,0.07);"
            ):
                if run.get("status") == "error":
                    with ui.row().classes("w-full items-start gap-2 p-3").style(
                        "background:#fff0f3; border:0.5px solid rgba(238,0,51,0.2); "
                        "border-left:3px solid #EE0033; border-radius:0 7px 7px 0;"
                    ):
                        ui.label(f"Lỗi: {run.get('error') or '(không có chi tiết)'}").classes("text-sm").style(
                            "color:#993035;"
                        )
                elif run.get("summary"):
                    info_box(lambda r=run: safe_markdown(r["summary"]))

                with ui.row().classes("w-full gap-4"):
                    with ui.column().classes("flex-1 gap-1"):
                        ui.label("DỮ LIỆU ĐẦU VÀO").classes("text-xs font-medium text-gray-500")
                        file_names = run.get("file_names")
                        if file_names:
                            for name in file_names:
                                with ui.row().classes("items-center gap-1"):
                                    ui.icon("description", color="#EE0033").style("font-size:13px;")
                                    ui.label(name).classes("text-sm text-gray-700")
                        elif run.get("n_files"):
                            ui.label(f"{run['n_files']} file đã dùng").classes("text-sm text-gray-700")
                        else:
                            ui.label("(không rõ)").classes("text-sm text-gray-700")
                    with ui.column().classes("flex-1 gap-1"):
                        ui.label("YÊU CẦU PHÂN TÍCH").classes("text-xs font-medium text-gray-500")
                        ui.label(run.get("user_query") or "(không có)").classes("text-sm text-gray-700 italic")

                log_entries = ExecutionLogger.load(run["run_id"])
                if log_entries:
                    ui.label("NHẬT KÝ THỰC THI").classes("text-xs font-medium text-gray-500")
                    with ui.column().classes("w-full gap-0 overflow-hidden").style(
                        "background:#fff; border:0.5px solid rgba(0,0,0,0.08); border-radius:8px;"
                    ):
                        with ui.row().classes("w-full gap-2 px-3 py-1.5").style("background:#F1EFE8;"):
                            ui.label("Bước").classes("text-xs font-medium").style("width:140px; color:#44494D;")
                            ui.label("Trạng thái").classes("text-xs font-medium").style("width:90px; color:#44494D;")
                            ui.label("Thời gian").classes("text-xs font-medium flex-1").style("color:#44494D;")
                        for entry in log_entries:
                            is_error = entry.get("result") == "error"
                            ts = entry.get("timestamp", "")
                            ts_short = ts[11:19] if len(ts) >= 19 else ts
                            decision = entry.get("decision") or {}
                            detail = decision.get("error") or decision.get("reason") or ""
                            with ui.row().classes("w-full gap-2 px-3 py-1.5 items-center").style(
                                "border-top:0.5px solid rgba(0,0,0,0.05);"
                                + ("background:#fff0f3;" if is_error else "")
                            ):
                                ui.label(entry.get("step", "")).classes("text-xs").style(
                                    f"width:140px; color:{'#EE0033' if is_error else '#555'};"
                                )
                                ui.label(entry.get("result", "")).classes("text-xs").style(
                                    f"width:90px; color:{'#EE0033' if is_error else '#3B6D11'};"
                                )
                                ui.label(f"{ts_short}  {detail}".strip()).classes("text-xs flex-1").style(
                                    f"color:{'#EE0033' if is_error else '#888'};"
                                )

                has_artifact = any(run.get(key) and os.path.exists(run[key]) for key in _ARTIFACT_BUTTONS)
                if has_artifact:
                    with ui.row().classes("gap-2 mt-1"):
                        for key, (label, icon) in _ARTIFACT_BUTTONS.items():
                            path = run.get(key)
                            if not (path and os.path.exists(path)):
                                continue
                            if key == "report_path":
                                ui.button(
                                    "Xem báo cáo",
                                    icon=icon,
                                    on_click=lambda p=path, r=run: _open_report(r, p),
                                    color="primary",
                                )
                                with open(path, "rb") as f:
                                    report_bytes = f.read()
                                ui.button(
                                    "Tải báo cáo",
                                    icon="download",
                                    on_click=lambda d=report_bytes, p=path: ui.download(
                                        d, filename=os.path.basename(p)
                                    ),
                                ).props("outline color=grey-7")
                            else:
                                with open(path, "rb") as f:
                                    file_bytes = f.read()
                                ui.button(
                                    label,
                                    icon=icon,
                                    on_click=lambda d=file_bytes, p=path: ui.download(d, filename=os.path.basename(p)),
                                ).props("outline color=grey-7")

        def render_one(run):
            run_id = run["run_id"]
            is_expanded = run_id in expanded_ids
            dt = _parse_run_time(run_id)
            duration = _format_duration(run.get("duration_seconds"))

            with ui.card().classes("w-full").style("padding:0; overflow:hidden;"):
                with ui.row().classes("w-full items-center gap-3 px-4 py-3"):
                    ui.element("div").style(
                        f"width:8px; height:8px; border-radius:50%; flex-shrink:0; "
                        f"background:{STATUS_DOT.get(run.get('status'), '#854F0B')};"
                    )

                    with ui.column().classes("gap-1 flex-1 cursor-pointer").on(
                        "click", lambda r=run_id: toggle(r)
                    ):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(run_id).classes("text-sm font-medium").style("color:#1a1a1a;")
                            if run.get("status") == "success":
                                ui.badge("Thành công", color="positive").classes("text-xs px-2")
                            else:
                                ui.badge("Thất bại", color="negative").classes("text-xs px-2")
                        with ui.row().classes("gap-2 flex-wrap"):
                            render_chip("database", run.get("problem") or "?", "#EE0033")
                            render_chip(
                                "bar_chart",
                                run.get("experiment_type") or "?",
                                EXPERIMENT_CHIP_COLOR.get(run.get("experiment_type"), "#44494D"),
                            )
                            if run.get("n_files"):
                                render_chip("description", f"{run['n_files']} file", "#5F5E5A")
                            if duration:
                                render_chip("schedule", duration, "#5F5E5A")
                            if run.get("source") == "chat":
                                render_chip("forum", "Qua chatbot", "#EE0033")

                    with ui.column().classes("gap-0 items-end").style("min-width:90px;"):
                        if dt:
                            ui.label(dt.strftime("%d/%m/%Y")).classes("text-xs font-medium text-gray-600")
                            ui.label(dt.strftime("%H:%M:%S")).classes("text-xs text-gray-400")

                    with ui.row().classes("gap-1"):
                        ui.button(icon="visibility", on_click=lambda r=run: view_run(r)).props(
                            "flat round dense color=grey-7"
                        )
                        ui.button(icon="delete", on_click=lambda r=run: delete_run(r)).props(
                            "flat round dense color=red-6"
                        )

                    ui.button(
                        icon="expand_less" if is_expanded else "expand_more",
                        on_click=lambda r=run_id: toggle(r),
                    ).props("flat round dense color=grey-7")

                if is_expanded:
                    render_detail(run)

        def render_list():
            list_zone.clear()
            runs = list(reversed(state.get("runs", [])))
            filtered = [r for r in runs if _matches_filters(r, filters)]
            with list_zone:
                if not runs:
                    _empty_state("Chưa có lần chạy nào", "Chạy thử 1 experiment để xem lịch sử ở đây.")
                elif not filtered:
                    _empty_state("Không tìm thấy kết quả phù hợp", "Thử đổi từ khoá tìm kiếm hoặc bộ lọc.")
                else:
                    for run in filtered:
                        render_one(run)

        def _empty_state(title, subtitle):
            with ui.column().classes("w-full items-center gap-2 p-12").style(
                "background:#fff; border:0.5px dashed rgba(0,0,0,0.15); border-radius:10px;"
            ):
                ui.icon("inbox", color="grey-4").style("font-size:36px;")
                ui.label(title).classes("text-sm font-medium text-gray-600")
                ui.label(subtitle).classes("text-xs text-gray-400")

        def on_search(e):
            filters["q"] = e.value or ""
            render_list()

        def on_select(e):
            filters["exp_type"] = e.value
            render_list()

        search_input.on_value_change(on_search)
        exp_select.on_value_change(on_select)

        render_stats()
        render_list()

        ui.button("Quay lại", on_click=lambda: ui.navigate.to("/")).props("outline color=grey-7").classes("mt-1")
