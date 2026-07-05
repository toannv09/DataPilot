"""Widget hiển thị dùng chung cho màn xác nhận / đang chạy / kết quả của run_experiment.py:
stat card, box cảnh báo/nhận xét viền trái màu, danh sách bước tiến trình, progress bar mỏng,
và terminal log giả lập.
"""

import re

from nicegui import ui

_SNAKE_CASE_UNDERSCORE_RE = re.compile(r"(?<=\w)_(?=\w)")


def safe_markdown(text):
    """ui.markdown() cho text LLM sinh ra — markdown2 (thư viện ui.markdown dùng) hiểu dấu `_`
    trong tên cột snake_case (vd "monthly_salary") là cú pháp in nghiêng, NUỐT MẤT dấu `_`
    khiến chữ dính liền ("monthlysalary") — đã repro trực tiếp với markdown2. Escape `_`
    thành `\\_` CHỈ khi nằm giữa 2 ký tự chữ/số liền nhau (không khoảng trắng) — in nghiêng/đậm
    thật luôn có khoảng trắng hoặc dấu câu cạnh `_`/`*` nên không bị ảnh hưởng.
    """
    if not isinstance(text, str):
        text = ""
    safe = _SNAKE_CASE_UNDERSCORE_RE.sub(r"\\_", text or "")
    ui.markdown(safe)


STATUS_STYLE = {
    "done": {"bg": "#eaf3de", "color": "#2E7D32", "icon": "check_circle"},
    "running": {"bg": "#fff0f3", "color": "#EE0033", "icon": None},  # icon=None -> vẽ spinner SVG
    "pending": {"bg": "#F7F7F8", "color": "#9E9E9E", "icon": "radio_button_unchecked"},
}

_SPINNER_CSS = """
@keyframes aeda-spin { to { transform: rotate(360deg); } }
.aeda-spinner { animation: aeda-spin 0.8s linear infinite; transform-origin: center; }
@keyframes aeda-blink { 50% { opacity: 0; } }
.aeda-cursor { animation: aeda-blink 1s step-start infinite; }
"""


def stat_card(icon, label, value, color="#EE0033", subtext=None):
    with ui.card().classes("flex-1 items-start gap-1"):
        with ui.row().classes("items-center gap-2"):
            with ui.element("div").classes("rounded-full flex items-center justify-center").style(
                f"background:{color}1A; width:30px; height:30px; flex-shrink:0;"
            ):
                ui.icon(icon, color=color).style("font-size:15px;")
            ui.label(label).classes("text-xs text-gray-500")
        ui.label(str(value)).classes("text-xl font-bold").style(f"color:{color};")
        if subtext:
            ui.label(subtext).classes("text-xs text-gray-400")


def info_box(content_builder, color="#EE0033", bg=None):
    """content_builder: callable() vẽ nội dung bên trong box viền trái màu `color`."""
    with ui.column().classes("w-full gap-1 p-3").style(
        f"background:{bg or color + '0D'}; border-left: 3px solid {color}; border-radius: 4px;"
    ):
        content_builder()


def progress_steps(steps):
    """steps: list[dict] — {"label": str, "status": "done"|"running"|"pending", "subtext": str|None}."""
    ui.add_css(_SPINNER_CSS)
    with ui.column().classes("w-full gap-2"):
        for step in steps:
            style = STATUS_STYLE[step["status"]]
            with ui.row().classes("items-center gap-3 w-full p-2").style(
                f"background:{style['bg']}; border-radius:7px;"
            ):
                if step["status"] == "running":
                    ui.html(
                        '<svg class="aeda-spinner" width="18" height="18" viewBox="0 0 24 24" '
                        f'fill="none" stroke="{style["color"]}" stroke-width="3">'
                        '<circle cx="12" cy="12" r="9" stroke-opacity="0.25"/>'
                        '<path d="M21 12a9 9 0 0 0-9-9"/></svg>'
                    )
                else:
                    ui.icon(style["icon"], color=style["color"]).style("font-size:18px;")
                with ui.column().classes("gap-0"):
                    ui.label(step["label"]).classes("text-sm font-medium").style(f"color:{style['color']};")
                    if step.get("subtext"):
                        ui.label(step["subtext"]).classes("text-xs text-gray-500")


def progress_bar(current, total):
    pct = int(min(current, total) / total * 100) if total else 0
    with ui.column().classes("w-full gap-1 mt-2"):
        with ui.element("div").classes("w-full").style(
            "height:5px; background:#eee; border-radius:3px; overflow:hidden;"
        ):
            ui.element("div").style(f"height:5px; background:#EE0033; width:{pct}%; transition: width .3s;")
        ui.label(f"Bước {current} / {total}").classes("text-xs text-gray-500")


def terminal_log(lines):
    """lines: list[(text, kind)] — kind in 'done' (xanh) / 'running' (đỏ + cursor) / 'muted' (xám timestamp)."""
    ui.add_css(_SPINNER_CSS)
    with ui.column().classes("w-full gap-0.5 p-3").style(
        "background:#1e1e1e; border-radius:8px; font-family: monospace; font-size:12px; max-height:220px; overflow-y:auto;"
    ):
        for text, kind in lines:
            if kind == "done":
                with ui.row().classes("gap-1 items-center"):
                    ui.label("$").style("color:#6a9955;")
                    ui.label(text).style("color:#4caf50;")
            elif kind == "running":
                with ui.row().classes("gap-1 items-center"):
                    ui.label(">").style("color:#EE0033;")
                    ui.label(text).style("color:#ff6b81;")
                    ui.label("_").classes("aeda-cursor").style("color:#ff6b81;")
            else:
                ui.label(text).style("color:#777;")
