"""Hiển thị biểu đồ PNG inline — tương đương ui/components/chart_viewer.py."""

from nicegui import ui


def _render_one(item):
    path = item["path"] if isinstance(item, dict) else item
    caption = item.get("caption", "") if isinstance(item, dict) else ""
    with ui.column().classes("gap-0"):
        ui.image(path).classes("w-full")
        if caption:
            ui.label(caption).classes("text-xs text-gray-500")


def render_charts(chart_paths, columns=2):
    """Hiển thị danh sách biểu đồ. Mỗi item có thể là str hoặc dict {"path","caption","wide"}.

    Chart đánh dấu "wide" (xem agents/eda_agent.py:WIDE_CHART_TOOLS — time series, lag
    correlation, pairplot, decomposition, missing heatmap) hiển thị full-width riêng từng
    dòng, không nhồi chung lưới `columns` cột với chart compact (distribution/boxplot/...) —
    tránh hàng lệch chiều cao và chart nhiều panel con bị bóp nhỏ khó đọc.
    """
    if not chart_paths:
        return

    normal = [c for c in chart_paths if not (isinstance(c, dict) and c.get("wide"))]
    wide = [c for c in chart_paths if isinstance(c, dict) and c.get("wide")]

    if normal:
        with ui.grid(columns=columns).classes("w-full gap-2"):
            for item in normal:
                _render_one(item)

    if wide:
        # ui.grid(columns=1) thay vì ui.column() — grid item tự stretch theo track width,
        # còn flex column con bên trong (_render_one) sẽ co theo kích thước ảnh nếu không có
        # track ép chiều rộng, khiến ảnh "wide" lại bị co nhỏ (đã xác nhận qua DOM inspect).
        with ui.grid(columns=1).classes("w-full gap-2" + (" mt-2" if normal else "")):
            for item in wide:
                _render_one(item)
