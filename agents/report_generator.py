"""Tổng hợp insight + biểu đồ + log thành báo cáo PDF/HTML."""

import base64
import json
import os
from datetime import datetime

import markdown
from jinja2 import Template
from weasyprint import HTML

from llm.client import MODEL_70B, call_llm
from llm.prompts.report_prompt import REPORT_SYSTEM, REPORT_USER

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "reports")

MAX_LIST_ITEMS = 5


def _truncate(obj):
    """Rút gọn list/dict lớn để tránh prompt vượt giới hạn token của LLM."""
    if isinstance(obj, list):
        items = [_truncate(x) for x in obj[:MAX_LIST_ITEMS]]
        if len(obj) > MAX_LIST_ITEMS:
            items.append(f"... và {len(obj) - MAX_LIST_ITEMS} mục khác")
        return items
    if isinstance(obj, dict):
        return {k: _truncate(v) for k, v in obj.items()}
    return obj

def _to_data_uri(path):
    """Đọc file ảnh PNG và encode base64 thành data URI để nhúng trực tiếp vào HTML."""
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


HTML_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Báo cáo phân tích dữ liệu</title>
<style>
body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
img { max-width: 100%; display: block; margin: 16px 0; }
figcaption { color: #666; font-size: 0.9em; margin-bottom: 16px; }
h1, h2, h3 { color: #2c3e50; }
</style>
</head>
<body>
{{ content }}
{% if charts %}
<h2>Biểu đồ</h2>
{% for chart in charts %}
<figure>
<img src="{{ chart.src }}" />
{% if chart.caption %}<figcaption>{{ chart.caption }}</figcaption>{% endif %}
</figure>
{% endfor %}
{% endif %}
</body>
</html>
""")


def _chart_path(item):
    """charts[] có thể là str (path) hoặc dict {"path":..., "caption":...} — chuẩn hóa về path."""
    return item["path"] if isinstance(item, dict) else item


def generate(dataset_info, eda_results, ml_results, execution_log, charts=None, output_format="html"):
    """Sinh báo cáo tiếng Việt từ kết quả EDA/ML + nhật ký, xuất vào outputs/reports/.

    output_format: "html" hoặc "pdf". Trả về path file báo cáo.
    """
    charts = [
        {"src": _to_data_uri(_chart_path(c)), "caption": c.get("caption", "") if isinstance(c, dict) else ""}
        for c in (charts or [])
        if os.path.exists(_chart_path(c))
    ]

    prompt = REPORT_USER.format(
        dataset_info=json.dumps(dataset_info, ensure_ascii=False, default=str),
        eda_results=json.dumps(_truncate(eda_results), ensure_ascii=False, default=str),
        ml_results=json.dumps(_truncate(ml_results), ensure_ascii=False, default=str) if ml_results else "Không có",
        execution_log=json.dumps(_truncate(execution_log), ensure_ascii=False, default=str),
    )
    content_md = call_llm(prompt, system=REPORT_SYSTEM, model=MODEL_70B)
    content_html = markdown.markdown(content_md)

    full_html = HTML_TEMPLATE.render(content=content_html, charts=charts)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_format == "pdf":
        path = os.path.join(OUTPUT_DIR, f"report_{timestamp}.pdf")
        HTML(string=full_html, base_url=OUTPUT_DIR).write_pdf(path)
    else:
        path = os.path.join(OUTPUT_DIR, f"report_{timestamp}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(full_html)

    return path
