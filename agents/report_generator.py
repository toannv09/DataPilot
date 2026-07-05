"""Tổng hợp insight + biểu đồ + log thành báo cáo PDF/HTML."""

import base64
import json
import os
from datetime import datetime

import markdown
from jinja2 import Template
from weasyprint import HTML

from llm.client import MODEL_DEFAULT, call_llm
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
body { font-family: Georgia, 'Times New Roman', serif; margin: 40px auto; max-width: 880px;
       line-height: 1.8; color: #333; }
h1, h2, h3 { font-family: Arial, sans-serif; color: #1a1a1a; }
h1 { font-size: 20px; font-weight: 700; border-left: 3px solid #EE0033; padding-left: 12px;
     margin: 30px 0 14px; }
h2 { font-size: 15px; font-weight: 600; color: #44494D; margin: 24px 0 10px; }
h3 { font-size: 13px; font-weight: 600; color: #44494D; margin: 16px 0 8px; }
p, li { font-size: 13px; }
table { width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 12px;
        margin: 14px 0; }
th { background: #F7F7F8; color: #44494D; font-weight: 600; text-align: left; padding: 7px 10px;
     border-bottom: 1px solid rgba(0,0,0,0.1); }
td { padding: 6px 10px; border-bottom: 1px solid rgba(0,0,0,0.06); color: #444; }
img { max-width: 100%; display: block; margin: 16px 0; border-radius: 6px; }
figcaption { font-family: Arial, sans-serif; color: #888; font-size: 11px; margin-bottom: 18px; }
hr { border: none; border-top: 0.5px solid rgba(0,0,0,0.08); margin: 26px 0; }
.aeda-report-footer { font-family: Arial, sans-serif; border-top: 0.5px solid rgba(0,0,0,0.08);
                       padding-top: 14px; margin-top: 32px; font-size: 10px; color: #bbb;
                       display: flex; justify-content: space-between; gap: 12px; }
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
<div class="aeda-report-footer">
<span>DataPilot · Sinh tự động · {{ generated_at }}</span>
<span>{{ problem_name }}{% if experiment_type %} · {{ experiment_type }}{% endif %}</span>
</div>
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
    content_md = call_llm(prompt, system=REPORT_SYSTEM, model=MODEL_DEFAULT)
    content_html = markdown.markdown(content_md)

    now = datetime.now()
    full_html = HTML_TEMPLATE.render(
        content=content_html,
        charts=charts,
        generated_at=now.strftime("%d/%m/%Y %H:%M"),
        problem_name=dataset_info.get("problem_name") or "",
        experiment_type=dataset_info.get("experiment_type") or "",
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    if output_format == "pdf":
        path = os.path.join(OUTPUT_DIR, f"report_{timestamp}.pdf")
        HTML(string=full_html, base_url=OUTPUT_DIR).write_pdf(path)
    else:
        path = os.path.join(OUTPUT_DIR, f"report_{timestamp}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(full_html)

    return path
