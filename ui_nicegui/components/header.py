"""Header bar đỏ Viettel dùng chung cho mọi trang — tách ra để đồng nhất navigation.

Gọi `render_header()` ngay sau `theme.apply()` ở đầu mỗi page function.
"""

from nicegui import ui


def render_header():
    with ui.header().style("background:#EE0033;").classes("items-center justify-between px-4"):
        ui.label("DataPilot").classes("text-xl font-bold text-white")
        with ui.row().classes("gap-1"):
            ui.button("Trang chủ", icon="home", on_click=lambda: ui.navigate.to("/")).props("flat color=white")
            ui.button(
                "Lịch sử", icon="history", on_click=lambda: ui.navigate.to("/run-history")
            ).props("flat color=white")

            def open_settings():
                ui.notify("Trang cài đặt chưa có — chức năng đang phát triển.", color="warning")

            ui.button("Cài đặt", icon="settings", on_click=open_settings).props("flat color=white")


def render_chip(icon, text, color):
    """Chip nhỏ bo tròn (icon + text màu nhạt trên nền {color}1A) — dùng chung ở mọi trang
    cần hiển thị 'tên bài toán' / 'loại experiment' bên cạnh tiêu đề.
    """
    with ui.row().classes("items-center gap-1 px-2 py-1 rounded-full").style(
        f"background:{color}1A; width:fit-content;"
    ):
        ui.icon(icon, color=color).style("font-size: 12px;")
        ui.label(text).style(f"color:{color};").classes("text-xs font-medium")


def render_breadcrumbs(items):
    """Thanh breadcrumb trắng, full chiều ngang, đặt ngay dưới `render_header()` (trước mọi
    container có padding) để đồng nhất giữa các trang.

    items: list[(label, path_or_None)] — path=None nghĩa là trang hiện tại (không click được).
    """
    with ui.row().classes("w-full items-center gap-1 px-8").style(
        "background:#fff; border-bottom:0.5px solid rgba(0,0,0,0.08); height:38px; font-size:12px; color:#888;"
    ):
        ui.icon("home", color="grey-5").style("font-size:13px;")
        for i, (label, path) in enumerate(items):
            if i > 0:
                ui.label("/").classes("text-gray-300")
            if path:
                ui.link(label, path).classes("no-underline").style("color:#888;")
            else:
                ui.label(label).style("color:#1a1a1a; font-weight:500;")
