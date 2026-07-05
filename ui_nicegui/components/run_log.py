"""Hiển thị execution log dạng bảng — tương đương ui/components/run_log.py."""

from nicegui import ui


def render_log(log_entries):
    """log_entries: list[dict] — mỗi dict là 1 bước thực thi."""
    if not log_entries:
        return

    ui.label("Nhật ký thực thi").classes("text-lg font-semibold mt-2")

    columns = []
    seen = set()
    for entry in log_entries:
        for k in entry.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)
    col_defs = [{"name": c, "label": c, "field": c} for c in columns]

    safe_rows = []
    for entry in log_entries:
        row = {}
        for k in columns:
            v = entry.get(k)
            row[k] = v if isinstance(v, (str, int, float, bool)) or v is None else str(v)
        safe_rows.append(row)

    ui.table(columns=col_defs, rows=safe_rows).classes("w-full")
