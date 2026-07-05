"""Tạo bài toán mới — form tên + mô tả. Tương đương ui/views/create_problem.py."""

from nicegui import ui

import state
import theme
from components.header import render_breadcrumbs, render_header

NAME_MAX_LEN = 80

_FORM_CSS = """
.aeda-field .q-field__control { border-radius: 8px !important; }
.aeda-field.q-field--outlined .q-field__control:before { border: 1px solid #d8d8d8; border-radius: 8px; }
.aeda-field.q-field--outlined.q-field--focused .q-field__control:before {
    border-color: #EE0033; border-width: 1px;
}
.aeda-field.q-field--outlined.q-field--focused .q-field__control {
    box-shadow: 0 0 0 3px rgba(238,0,51,0.08);
}
"""


def _required_label(text):
    with ui.row().classes("items-center gap-1 mb-1"):
        ui.label(text).classes("text-sm font-medium text-gray-700")
        ui.label("*").classes("text-sm font-medium").style("color:#EE0033")


@ui.page("/create-problem")
def create_problem_page():
    theme.apply()
    state.ensure_defaults()
    ui.add_css(_FORM_CSS)

    render_header()
    render_breadcrumbs([("Trang chủ", "/"), ("Tạo bài toán mới", None)])

    with ui.column().classes("w-full items-center").style("background:#F7F7F8; min-height:100vh; padding:24px;"):
        with ui.column().classes("w-full").style("max-width: 640px;"):
            with ui.card().classes("w-full mt-3"):
                with ui.row().classes("items-center gap-3"):
                    with ui.element("div").classes("rounded-full flex items-center justify-center").style(
                        "background:#EE00331A; width:40px; height:40px; flex-shrink:0;"
                    ):
                        ui.icon("add_task", color="#EE0033")
                    with ui.column().classes("gap-0"):
                        ui.label("Tạo bài toán mới").classes("text-lg font-semibold")
                        ui.label("Mô tả bài toán bạn muốn phân tích — đây sẽ là điểm bắt đầu cho mọi experiment.").classes(
                            "text-sm text-gray-500"
                        )

                ui.separator().classes("my-3")

                _required_label("Tên bài toán")

                def update_char_count():
                    char_count_label.text = f"{len(name_input.value or '')}/{NAME_MAX_LEN}"

                name_input = (
                    ui.input(placeholder="Vd: Phân tích nghỉ việc nhân sự Q1", on_change=update_char_count)
                    .props(f"outlined maxlength={NAME_MAX_LEN}")
                    .classes("w-full aeda-field")
                )
                char_count_label = ui.label(f"0/{NAME_MAX_LEN}").classes("text-xs text-gray-400 self-end")

                ui.label("Mô tả bài toán").classes("text-sm font-medium text-gray-700 mb-1 mt-3")
                desc_input = ui.textarea(
                    placeholder="Vd: Phân tích các yếu tố ảnh hưởng tới việc nhân viên nghỉ việc trong quý 1..."
                ).props("outlined").classes("w-full aeda-field")
                ui.label("Mô tả ngắn gọn mục tiêu phân tích — giúp AI hiểu đúng ngữ cảnh khi đưa ra nhận xét.").classes(
                    "text-xs text-gray-400 mt-1"
                )

                with ui.row().classes("items-start gap-2 mt-4 w-full p-3").style(
                    "background:#FFF1F3; border-left: 3px solid #EE0033; border-radius: 6px;"
                ):
                    ui.icon("lightbulb", color="#EE0033").style("font-size: 18px; margin-top: 2px;")
                    ui.label(
                        "Sau khi tạo, bạn sẽ chọn loại experiment (Khám phá dữ liệu, Huấn luyện mô hình...) "
                        "và upload dữ liệu để bắt đầu phân tích."
                    ).classes("text-sm text-gray-700")

                ui.separator().classes("my-4")

                with ui.row().classes("w-full justify-between"):
                    ui.button("Quay lại", on_click=lambda: ui.navigate.to("/")).props("outline color=grey-7")

                    def submit():
                        if not name_input.value or not name_input.value.strip():
                            ui.notify("Vui lòng nhập tên bài toán.", color="negative")
                            return
                        problems = state.get("problems", [])
                        problems.append({"name": name_input.value.strip(), "description": desc_input.value or ""})
                        state.set_value("problems", problems)
                        state.set_value("current_problem_idx", len(problems) - 1)
                        ui.navigate.to("/select-experiment")

                    ui.button("Tạo và tiếp tục", icon="arrow_forward", on_click=submit, color="primary")
