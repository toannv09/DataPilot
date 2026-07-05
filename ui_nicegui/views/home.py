"""Trang chủ — danh sách bài toán đã tạo. Tương đương ui/views/home.py.

Giao diện nâng cấp: header đỏ Viettel (dùng chung qua components/header.py), nền xám nhạt,
stat card, problem card có badge/accent/hover, empty state.
"""

from nicegui import ui

import state
import theme
from components.experiment_card import render_problem_card
from components.header import render_header

RECENT_LIMIT = 5

_CARD_CSS = """
.problem-card { border-left: 3px solid #EE0033; transition: box-shadow .15s ease, border-color .15s ease; }
.problem-card:hover { border-left-color: #b3001f; box-shadow: 0 2px 12px rgba(0,0,0,0.10); }
"""


def _stat_card(icon, color, label, value):
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-3 no-wrap"):
            with ui.element("div").classes("rounded-full flex items-center justify-center").style(
                f"background:{color}1A; width:40px; height:40px; flex-shrink:0;"
            ):
                ui.icon(icon, color=color)
            with ui.column().classes("gap-0"):
                ui.label(label).classes("text-sm text-gray-500")
                ui.label(str(value)).classes("text-2xl font-bold")


def _render_empty_state():
    with ui.column().classes("w-full items-center justify-center gap-1 py-16").style(
        "border: 2px dashed #d0d0d0; border-radius: 12px; background: white; margin-top: 16px;"
    ):
        ui.icon("inbox", color="grey-5").style("font-size: 48px;")
        ui.label("Chưa có bài toán nào").classes("text-lg font-semibold text-gray-700 mt-2")
        ui.label("Bắt đầu bằng cách tạo bài toán đầu tiên của bạn").classes("text-sm text-gray-500")
        ui.button(
            "Tạo bài toán mới", icon="add", color="primary", on_click=lambda: ui.navigate.to("/create-problem")
        ).classes("mt-3")


@ui.page("/")
def home_page():
    theme.apply()
    state.ensure_defaults()
    ui.add_css(_CARD_CSS)

    render_header()

    with ui.column().classes("w-full").style("background:#F7F7F8; min-height:100vh; padding:24px;"):
        problems = state.get("problems", [])

        show_all_box = {"value": False}

        def toggle_show_all():
            show_all_box["value"] = not show_all_box["value"]
            show_all_btn.text = "Thu gọn ←" if show_all_box["value"] else "Xem tất cả →"
            render_list()

        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Danh sách bài toán").classes("text-2xl font-bold")
                ui.label("Quản lý và theo dõi các bài toán phân tích dữ liệu của bạn").classes(
                    "text-sm text-gray-500"
                )
            with ui.row().classes("items-center gap-2"):
                show_all_btn = ui.button("Xem tất cả →", on_click=toggle_show_all).props(
                    "flat color=primary"
                ).classes("text-sm")
                if len(problems) <= RECENT_LIMIT:
                    show_all_btn.visible = False
                ui.button(
                    "Dùng chatbot",
                    icon="forum",
                    on_click=lambda: ui.navigate.to("/chat"),
                ).props("outline color=primary")
                ui.button(
                    "Tạo bài toán mới",
                    icon="add",
                    color="primary",
                    on_click=lambda: ui.navigate.to("/create-problem"),
                )

        stats_zone = ui.grid(columns=3).classes("w-full gap-4 mt-4")

        list_container = ui.column().classes("w-full mt-4")

        def delete_problem(problem):
            # Xoá theo identity (không theo index) — index dịch chuyển ngay sau khi xoá 1 phần
            # tử, dùng identity tránh xoá nhầm bài toán khác nếu có 2 lần render chồng nhau.
            remaining = [p for p in state.get("problems", []) if p is not problem]
            state.set_value("problems", remaining)

            # Xoá CẢ lịch sử (runs) thuộc bài toán này — kể cả file log trên đĩa (yêu cầu của
            # người dùng: xoá bài toán thì xoá luôn lịch sử liên quan, không để rác lại).
            matching_run_ids = [r["run_id"] for r in state.get("runs", []) if r.get("problem") == problem["name"]]
            for run_id in matching_run_ids:
                state.delete_run_record(run_id)

            # current_problem_idx trỏ theo INDEX cũ — index của các bài toán sau phần tử vừa xoá
            # đều dịch lùi 1, giữ nguyên giá trị cũ dễ trỏ nhầm sang bài toán khác. Reset về None,
            # bắt người dùng bấm "Chọn" lại (đã có sẵn guard ở select-experiment.py cho ca này).
            state.set_value("current_problem_idx", None)

            ui.notify(
                f'Đã xoá bài toán "{problem["name"]}" và {len(matching_run_ids)} lịch sử liên quan.',
                color="positive",
            )
            # show_all_btn.visible chỉ tính 1 lần lúc tải trang — xoá bớt bài toán có thể khiến
            # số lượng tụt xuống dưới RECENT_LIMIT, phải tính lại cho khớp (khác lúc TẠO bài toán
            # mới, luôn điều hướng sang trang khác nên load lại trang home sẽ tự tính đúng).
            show_all_btn.visible = len(remaining) > RECENT_LIMIT
            render_stats()
            render_list()

        def render_stats():
            stats_zone.clear()
            current_problems = state.get("problems", [])
            current_runs = state.get("runs", [])
            n_success_now = sum(1 for r in current_runs if r.get("status") == "success")
            with stats_zone:
                _stat_card("folder", "#EE0033", "Số bài toán", len(current_problems))
                _stat_card("play_circle", "#44494D", "Số lần chạy", len(current_runs))
                _stat_card("check_circle", "#2E7D32", "Thành công", n_success_now)

        def render_list():
            list_container.clear()
            current_problems = state.get("problems", [])
            current_runs = state.get("runs", [])
            with list_container:
                if not current_problems:
                    _render_empty_state()
                    return

                indexed = list(enumerate(current_problems))[::-1]  # mới tạo hiện trước
                visible = indexed if show_all_box["value"] else indexed[:RECENT_LIMIT]

                for idx, problem in visible:
                    last_run = next(
                        (r for r in reversed(current_runs) if r.get("problem") == problem["name"]), None
                    )

                    def select(idx=idx):
                        state.set_value("current_problem_idx", idx)
                        ui.navigate.to("/select-experiment")

                    def delete(problem=problem):
                        delete_problem(problem)

                    render_problem_card(problem, last_run, on_select=select, on_delete=delete)

        render_stats()
        render_list()
