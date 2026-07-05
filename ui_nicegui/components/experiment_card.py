"""Card hiển thị thông tin bài toán/experiment — tương đương ui/components/experiment_card.py."""

from nicegui import ui


def render_card(title, description, on_click, button_label="Chọn"):
    """Hiển thị 1 card với tiêu đề, mô tả và nút bấm. on_click: callback khi bấm nút.

    Dùng cho card đơn giản (select_experiment.py) — không đổi để khỏi ảnh hưởng chỗ đó.
    """
    with ui.card().classes("w-full"):
        ui.label(title).classes("text-lg font-bold")
        ui.label(description).classes("text-sm text-gray-600")
        ui.button(button_label, on_click=on_click).props("outline")


def render_template_card(template, on_click):
    """Card chọn loại experiment (select_experiment.py) — icon màu riêng theo loại, tag kỹ
    thuật + thời gian ước tính, border-top/badge nổi bật cho EDA, accent tối cho Full Pipeline.
    Hover effect (translateY + shadow đỏ) định nghĩa ở class "template-card" (xem select_experiment.py).

    time_estimate là ước lượng định hướng cho UX, không phải số đo benchmark thật.
    """
    border_color = template.get("border_color", "#e5e5e5")
    # h-full + flex-col: card giãn đều theo hàng (CSS grid tự stretch), nội dung bên trong bọc
    # trong khối flex-grow để đẩy nút "Chọn" luôn dính đáy, không bị lệch giữa các card cùng hàng
    # do mô tả/số tag dài ngắn khác nhau.
    with ui.card().classes("template-card w-full h-full relative flex flex-col"):
        ui.element("div").style(
            f"position:absolute; top:0; left:0; right:0; height:3px; background:{border_color}; "
            "border-radius: 4px 4px 0 0;"
        )

        if template.get("badge"):
            ui.badge(template["badge"], color="primary").classes("absolute top-3 right-3 text-xs")

        with ui.column().classes("gap-0 flex-grow"):
            with ui.row().classes("items-center gap-2 mt-1"):
                with ui.element("div").classes("rounded-full flex items-center justify-center").style(
                    f"background:{template['color']}1A; width:36px; height:36px; flex-shrink:0;"
                ):
                    ui.icon(template["icon"], color=template["color"])
                ui.label(template["name"]).classes("text-lg font-semibold")

            ui.label(template["description"]).classes("text-sm text-gray-600 mt-1 leading-relaxed")

            with ui.row().classes("gap-1 mt-2 flex-wrap"):
                for tag in template.get("tags", []):
                    # Dùng ui.label tự style thay vì ui.badge — QBadge có class CSS mặc định
                    # (bg-primary) đè lên .style() inline, khiến mọi tag ra cùng màu đỏ dù set khác.
                    ui.label(tag).style(
                        f"background:{template['color']}26; color:{template['color']}; "
                        "padding: 2px 10px; border-radius: 999px; font-weight: 500;"
                    ).classes("text-sm")

            with ui.row().classes("items-center gap-1 mt-2"):
                ui.icon("schedule", color="grey-5").style("font-size: 14px;")
                ui.label(template.get("time_estimate", "")).classes("text-xs text-gray-400")

        ui.button("Chọn", on_click=on_click, color=template.get("button_color", "primary")).classes("w-full mt-3")


def _status_chip(text, bg, color):
    """Chip nền màu nhạt + chữ đậm màu — dùng thay ui.badge(outline=...) vì badge outline với
    grey-5 + text màu đen render quá mờ, khó đọc trên nền trắng."""
    ui.label(text).classes("text-sm px-2 py-0.5 rounded-full font-medium").style(f"background:{bg}; color:{color};")


def render_problem_card(problem, last_run, on_select, on_delete):
    """Card bài toán cho trang chủ — đậm hơn render_card: accent đỏ bên trái, badge loại
    experiment + trạng thái lần chạy cuối (suy ra từ `runs`, không phải dữ liệu lưu riêng),
    2 nút (Xoá/Chọn), hover effect (định nghĩa ở class "problem-card", xem home.py).

    last_run: dict run gần nhất khớp problem này (theo problem_name) hoặc None nếu chưa chạy.
    Không có badge "số file" — dữ liệu này không được lưu lại ở cấp problem trong state hiện tại
    (file chỉ tồn tại tạm trong 1 experiment, không persist theo problem).
    """
    with ui.card().classes("problem-card w-full"):
        with ui.row().classes("w-full items-start justify-between no-wrap"):
            with ui.column().classes("gap-1 flex-1 min-w-0"):
                ui.label(problem["name"]).classes("text-lg font-medium")
                if problem.get("description"):
                    ui.label(problem["description"]).classes("text-sm text-gray-500")

                with ui.row().classes("gap-2"):
                    if last_run:
                        _status_chip(last_run["experiment_type"], "#e8e9ea", "#2C2C2A")
                        if last_run["status"] == "success":
                            _status_chip("Thành công", "#eaf3de", "#27500A")
                        else:
                            _status_chip("Lỗi", "#fff0f3", "#993035")
                    else:
                        _status_chip("Chưa chạy", "#F1EFE8", "#5F5E5A")

            with ui.row().classes("gap-2 flex-shrink-0"):
                ui.button("Xoá", icon="delete", on_click=on_delete).props("outline color=red-6")
                ui.button("Chọn", on_click=on_select, color="primary")
