"""Xem và download báo cáo HTML/PDF. Tương đương ui/views/report.py.

Layout 2 cột: sidebar trái cố định 200px (thông tin run + mục lục click-to-jump + nút hành
động) và vùng nội dung báo cáo bên phải (topbar + iframe có toolbar riêng). Mục lục được dựng
động bằng cách parse thẻ <h1>/<h2> ngay trong HTML báo cáo (nội dung do LLM sinh ra, không có
cấu trúc section cố định) rồi gắn id — không có cách nào biết trước section trừ khi đọc lại
chính file đã sinh.
"""

import base64
import os
import re
from datetime import datetime

from nicegui import run as nicegui_run, ui

import state
import theme
from components.header import render_breadcrumbs, render_chip, render_header

_HEADING_RE = re.compile(r"<(h[12])([^>]*)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

_PAGE_CSS = """
.aeda-toc-item { transition: background .12s; }
.aeda-toc-item:hover { background:#F7F7F8; }
.aeda-toc-item.aeda-toc-active { background:#fff0f3 !important; }
.aeda-toc-item.aeda-toc-active .aeda-toc-text { color:#EE0033 !important; font-weight:500; }
"""

# Script được nhúng vào CHÍNH iframe báo cáo (không phải trang cha) — lắng nghe postMessage để
# scroll tới section, đồng thời tự báo cáo section đang hiển thị (scroll-spy) ra ngoài cho
# trang cha highlight đúng mục lục. data URI khiến iframe có origin riêng nhưng postMessage
# không bị giới hạn bởi same-origin nên vẫn dùng được.
_TOC_IFRAME_SCRIPT = """
<script>
(function () {
  window.addEventListener('message', function (ev) {
    if (ev.data && ev.data.type === 'aeda-scroll') {
      var el = document.getElementById(ev.data.id);
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  });
  var headings = Array.prototype.slice.call(document.querySelectorAll('[id^="aeda-section-"]'));
  function reportActive() {
    var active = headings.length ? headings[0].id : null;
    for (var i = 0; i < headings.length; i++) {
      if (headings[i].getBoundingClientRect().top <= 90) active = headings[i].id;
    }
    window.parent.postMessage({type: 'aeda-active', id: active}, '*');
  }
  window.addEventListener('scroll', reportActive);
  setTimeout(reportActive, 200);
})();
</script>
"""


def _format_duration(seconds):
    if seconds is None:
        return None
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


def _parse_run_time(run_id):
    try:
        return datetime.strptime(run_id, "%Y%m%d_%H%M%S")
    except (ValueError, TypeError):
        return None


def _inject_toc_anchors(html):
    """Gắn id vào từng <h1>/<h2> trong nội dung báo cáo, trả về (html_mới, toc[{id, text}])."""
    toc = []
    counter = {"n": 0}

    def repl(match):
        tag, attrs, inner = match.group(1), match.group(2), match.group(3)
        text = _TAG_RE.sub("", inner).strip()
        if not text:
            return match.group(0)
        counter["n"] += 1
        anchor_id = f"aeda-section-{counter['n']}"
        toc.append({"id": anchor_id, "text": text})
        return f'<{tag} id="{anchor_id}"{attrs}>{inner}</{tag}>'

    return _HEADING_RE.sub(repl, html), toc


@ui.page("/report")
def report_page():
    theme.apply()
    state.ensure_defaults()
    render_header()

    breadcrumb_trail = state.get("report_breadcrumbs") or [("Lịch sử chạy", "/run-history")]
    render_breadcrumbs([*breadcrumb_trail, ("Báo cáo", None)])

    return_path = state.get("report_return_path") or "/run-history"
    report_path = state.get("report_path")

    if not report_path or not os.path.exists(report_path):
        with ui.column().classes("w-full items-center justify-center gap-2 py-20").style(
            "background:#F7F7F8; min-height:calc(100vh - 90px);"
        ):
            ui.icon("description_off", color="grey-5").style("font-size:44px;")
            ui.label("Chưa có báo cáo nào được sinh.").classes("text-gray-500")
            ui.button("Quay lại", on_click=lambda: ui.navigate.to(return_path)).props("outline color=grey-7")
        return

    ui.add_css(_PAGE_CSS)

    meta = state.get("report_meta") or {}
    with open(report_path, "rb") as f:
        raw = f.read()
    filename = os.path.basename(report_path)
    is_html = report_path.endswith(".html")

    toc = []
    if is_html:
        html_text = raw.decode("utf-8", errors="ignore")
        html_text, toc = _inject_toc_anchors(html_text)
        if "</body>" in html_text:
            html_text = html_text.replace("</body>", _TOC_IFRAME_SCRIPT + "</body>")
        else:
            html_text += _TOC_IFRAME_SCRIPT
        b64 = base64.b64encode(html_text.encode("utf-8")).decode()
        iframe_src = f"data:text/html;base64,{b64}"
    else:
        b64 = base64.b64encode(raw).decode()
        iframe_src = f"data:application/pdf;base64,{b64}"

    def do_download():
        ui.download(raw, filename=filename, media_type="text/html" if is_html else "application/pdf")

    async def do_export_pdf():
        if not is_html:
            ui.download(raw, filename=filename, media_type="application/pdf")
            return
        ui.notify("Đang xuất PDF...", color="info", timeout=0)

        def _to_pdf():
            from weasyprint import HTML
            return HTML(
                string=html_text,
                base_url=os.path.dirname(os.path.abspath(report_path)),
            ).write_pdf()

        pdf_bytes = await nicegui_run.io_bound(_to_pdf)
        pdf_name = filename.replace(".html", ".pdf")
        ui.download(pdf_bytes, filename=pdf_name, media_type="application/pdf")
        ui.notify("Đã xuất PDF", color="positive")

    def do_fullscreen():
        ui.run_javascript("document.getElementById('aeda-iframe-card').requestFullscreen();")

    def scroll_to(anchor_id):
        ui.run_javascript(
            "document.getElementById('aeda-report-iframe').contentWindow.postMessage("
            f"{{type:'aeda-scroll', id:'{anchor_id}'}}, '*');"
        )

    is_success = meta.get("status") in (None, "success")
    dt = _parse_run_time(meta.get("run_id"))
    duration = _format_duration(meta.get("duration_seconds"))

    with ui.row().classes("w-full items-start gap-4 no-wrap").style(
        "background:#F7F7F8; min-height:calc(100vh - 90px); padding:24px 32px;"
    ):

        with ui.column().classes("gap-3").style("width:200px; flex-shrink:0; position:sticky; top:24px;"):
            with ui.card().classes("w-full gap-0").style("padding:0;"):
                with ui.row().classes("items-center gap-2 px-3 py-2 w-full").style(
                    "border-bottom:0.5px solid rgba(0,0,0,0.07);"
                ):
                    ui.icon("info", color="#EE0033").style("font-size:14px;")
                    ui.label("Thông tin").classes("text-xs font-medium").style("color:#44494D;")
                with ui.column().classes("gap-2 px-3 py-3 w-full"):
                    if meta.get("problem"):
                        with ui.column().classes("gap-0"):
                            ui.label("Bài toán").classes("text-xs text-gray-400")
                            ui.label(meta["problem"]).classes("text-xs font-medium")
                    if meta.get("experiment_type"):
                        with ui.column().classes("gap-1"):
                            ui.label("Experiment").classes("text-xs text-gray-400")
                            render_chip("bar_chart", meta["experiment_type"], "#44494D")
                    if meta.get("run_id"):
                        with ui.column().classes("gap-0"):
                            ui.label("Run ID").classes("text-xs text-gray-400")
                            ui.label(meta["run_id"]).classes("text-xs").style(
                                "font-family:monospace; color:#666;"
                            )
                    if meta.get("status"):
                        with ui.column().classes("gap-1"):
                            ui.label("Trạng thái").classes("text-xs text-gray-400")
                            render_chip(
                                "check" if is_success else "close",
                                "Thành công" if is_success else "Thất bại",
                                "#2E7D32" if is_success else "#EE0033",
                            )
                    if dt or duration:
                        with ui.column().classes("gap-0"):
                            ui.label("Thời gian").classes("text-xs text-gray-400")
                            ui.label(
                                " · ".join(filter(None, [duration, dt.strftime("%d/%m/%Y %H:%M") if dt else None]))
                            ).classes("text-xs font-medium")
                    if not meta:
                        ui.label("(không có thông tin run)").classes("text-xs text-gray-400 italic")

            toc_rows = []
            if toc:
                with ui.card().classes("w-full gap-0").style("padding:0;"):
                    with ui.row().classes("items-center gap-2 px-3 py-2 w-full").style(
                        "border-bottom:0.5px solid rgba(0,0,0,0.07);"
                    ):
                        ui.icon("list", color="#EE0033").style("font-size:14px;")
                        ui.label("Mục lục").classes("text-xs font-medium").style("color:#44494D;")
                    with ui.column().classes("gap-0 px-2 py-2 w-full"):
                        for i, item in enumerate(toc, start=1):
                            row = (
                                ui.row()
                                .classes("aeda-toc-item items-center gap-2 px-2 py-1.5 cursor-pointer rounded w-full no-wrap")
                                .on("click", lambda a=item["id"]: scroll_to(a))
                            )
                            with row:
                                ui.label(str(i)).classes("text-xs text-gray-400").style("min-width:14px;")
                                ui.label(item["text"]).classes("aeda-toc-text text-xs text-gray-700").style(
                                    "overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"
                                )
                            toc_rows.append((item["id"], row.html_id))

            if toc_rows:
                toc_map_js = ", ".join(f"'{section_id}': '{dom_id}'" for section_id, dom_id in toc_rows)
                ui.run_javascript(
                    f"""
                    window.__aedaTocMap = {{{toc_map_js}}};
                    if (!window.__aedaTocListener) {{
                        window.__aedaTocListener = true;
                        window.addEventListener('message', function (ev) {{
                            if (!ev.data || ev.data.type !== 'aeda-active') return;
                            Object.values(window.__aedaTocMap || {{}}).forEach(function (domId) {{
                                var el = document.getElementById(domId);
                                if (el) el.classList.remove('aeda-toc-active');
                            }});
                            var target = (window.__aedaTocMap || {{}})[ev.data.id];
                            if (target) {{
                                var el = document.getElementById(target);
                                if (el) el.classList.add('aeda-toc-active');
                            }}
                        }});
                    }}
                    """
                )

            with ui.column().classes("gap-2 w-full"):
                ui.button(
                    "Tải " + ("HTML" if is_html else "PDF"),
                    icon="download",
                    on_click=do_download,
                    color="primary",
                ).classes("w-full")
                if is_html:
                    ui.button("Xuất PDF", icon="picture_as_pdf", on_click=do_export_pdf).props(
                        "outline color=grey-7"
                    ).classes("w-full")
                ui.button("Quay lại", icon="arrow_back", on_click=lambda: ui.navigate.to(return_path)).props(
                    "outline color=grey-7"
                ).classes("w-full")

        with ui.column().classes("flex-1 gap-3").style("min-width:0;"):
            with ui.row().classes("w-full items-center justify-between p-3").style(
                "background:#fff; border:0.5px solid rgba(0,0,0,0.09); border-radius:10px;"
            ):
                with ui.row().classes("items-center gap-3"):
                    ui.label("Báo cáo phân tích dữ liệu").classes("text-sm font-medium").style("color:#1a1a1a;")
                    render_chip(
                        "check" if is_success else "close",
                        "Thành công" if is_success else "Thất bại",
                        "#2E7D32" if is_success else "#EE0033",
                    )
                with ui.row().classes("gap-2"):
                    ui.button(
                        "Quay lại", icon="arrow_back", on_click=lambda: ui.navigate.to(return_path)
                    ).props("outline dense color=grey-7").classes("text-xs")
                    ui.button(icon="fullscreen", on_click=do_fullscreen).props("outline dense color=grey-7")
                    ui.button("Tải " + ("HTML" if is_html else "PDF"), icon="download", on_click=do_download).props(
                        "outline dense color=grey-7"
                    ).classes("text-xs")
                    if is_html:
                        ui.button("Xuất PDF", icon="picture_as_pdf", on_click=do_export_pdf, color="primary").props(
                            "dense"
                        ).classes("text-xs")

            with ui.column().classes("w-full gap-0").props("id=aeda-iframe-card").style(
                "background:#fff; border:0.5px solid rgba(0,0,0,0.09); border-radius:10px; overflow:hidden;"
            ):
                with ui.row().classes("w-full items-center justify-between px-3 py-2 no-wrap").style(
                    "background:#fafafa; border-bottom:0.5px solid rgba(0,0,0,0.07);"
                ):
                    with ui.row().classes("items-center gap-2"):
                        with ui.row().classes("gap-1"):
                            ui.element("div").style(
                                "width:9px; height:9px; border-radius:50%; background:#EE0033; opacity:.5;"
                            )
                            ui.element("div").style(
                                "width:9px; height:9px; border-radius:50%; background:#faeeda; "
                                "border:1px solid #854F0B; opacity:.7;"
                            )
                            ui.element("div").style(
                                "width:9px; height:9px; border-radius:50%; background:#eaf3de; "
                                "border:1px solid #3B6D11; opacity:.7;"
                            )
                        ui.icon("description", color="grey-5").style("font-size:13px;")
                        ui.label(filename).classes("text-xs text-gray-500")
                    if is_html:
                        with ui.row().classes("gap-1 items-center"):
                            ui.button(icon="zoom_out", on_click=lambda: ui.run_javascript("aedaSetZoom(-10)")).props(
                                "flat dense round size=sm color=grey-7"
                            )
                            ui.label("100%").props("id=aeda-zoom-label").classes("text-xs text-gray-500").style(
                                "min-width:34px; text-align:center;"
                            )
                            ui.button(icon="zoom_in", on_click=lambda: ui.run_javascript("aedaSetZoom(10)")).props(
                                "flat dense round size=sm color=grey-7"
                            )

                ui.html(
                    f'<iframe id="aeda-report-iframe" src="{iframe_src}" '
                    'style="width:100%;height:800px;border:none;display:block;"></iframe>',
                    sanitize=False,
                ).classes("w-full")

    if is_html:
        ui.run_javascript(
            """
            if (!window.aedaSetZoom) {
                window.__aedaZoom = 100;
                window.aedaSetZoom = function (delta) {
                    window.__aedaZoom = Math.max(50, Math.min(150, window.__aedaZoom + delta));
                    var f = document.getElementById('aeda-report-iframe');
                    if (f) f.style.zoom = window.__aedaZoom + '%';
                    var l = document.getElementById('aeda-zoom-label');
                    if (l) l.textContent = window.__aedaZoom + '%';
                };
            }
            """
        )
