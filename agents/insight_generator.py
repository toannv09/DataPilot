"""LLM diễn giải kết quả EDA theo domain bằng tiếng Việt."""

import json
import re

from llm.client import MODEL_DEFAULT, call_llm
from llm.prompts.insight_prompt import DOMAIN_GENERIC, INSIGHT_SYSTEM, INSIGHT_USER

MAX_LIST_ITEMS = 20
# Hard cap tổng kích thước string trước khi nhét vào prompt (~ 50k token ở mức 4 char/token).
MAX_PROMPT_CHARS = 200_000

_CHART_TAG_RE = re.compile(r"\[\[chart:(\d+)\]\]")


def _format_chart_list(charts):
    """Liệt kê chart do planner chọn (source='planner', có id) để LLM gắn thẻ [[chart:ID]].

    Chart loại 'trigger' (tổng quan, tự động trigger ở Phase 1) không đưa vào đây —
    chúng luôn hiển thị riêng, không cần khớp với câu insight nào.
    """
    linkable = [c for c in (charts or []) if c.get("source") == "planner" and c.get("id") is not None]
    if not linkable:
        return "Biểu đồ có sẵn: (không có)"

    lines = ["Biểu đồ có sẵn (chỉ để tham khảo gắn thẻ liên kết, không phải dữ liệu phân tích):"]
    for c in linkable:
        lines.append(f"- [[chart:{c['id']}]] {c.get('caption', '')}")
    return "\n".join(lines)


def split_insight_by_charts(text, charts):
    """Tách insight text theo thẻ [[chart:ID]] thành list segment {"type": "text"|"chart", ...}.

    Trả về (segments, used_ids). Tag tham chiếu chart không tồn tại hoặc bị lặp sẽ bị bỏ qua
    (không hiện text thẻ thô ra ngoài). Chart 'planner' nào không được gắn thẻ thì KHÔNG nằm
    trong segments — nơi gọi tự render fallback dựa trên used_ids.
    """
    chart_by_id = {c["id"]: c for c in (charts or []) if c.get("id") is not None}
    segments = []
    used_ids = set()
    pos = 0
    for m in _CHART_TAG_RE.finditer(text or ""):
        chunk = text[pos:m.start()]
        if chunk.strip():
            segments.append({"type": "text", "content": chunk})
        chart_id = int(m.group(1))
        chart = chart_by_id.get(chart_id)
        if chart is not None and chart_id not in used_ids:
            segments.append({"type": "chart", "chart": chart})
            used_ids.add(chart_id)
        pos = m.end()
    tail = (text or "")[pos:]
    if tail.strip():
        segments.append({"type": "text", "content": tail})
    return segments, used_ids


def _truncate(obj, max_items=MAX_LIST_ITEMS):
    """Rút gọn list dài (vd outlier_indices) để tránh prompt vượt giới hạn token của LLM."""
    if isinstance(obj, list):
        items = [_truncate(x, max_items) for x in obj[:max_items]]
        if len(obj) > max_items:
            items.append(f"... và {len(obj) - max_items} mục khác")
        return items
    if isinstance(obj, dict):
        return {k: _truncate(v, max_items) for k, v in obj.items()}
    return obj


def _serialize(eda_results):
    """Serialize kết quả EDA thành JSON, rút gọn dần nếu vẫn vượt MAX_PROMPT_CHARS."""
    for max_items in (MAX_LIST_ITEMS, 5, 1):
        serialized = json.dumps(_truncate(eda_results, max_items), ensure_ascii=False, default=str)
        if len(serialized) <= MAX_PROMPT_CHARS:
            return serialized

    return serialized[:MAX_PROMPT_CHARS] + "... (đã rút gọn do quá lớn)"


def generate(eda_results, domain_context="", hypotheses=None, charts=None):
    """Diễn giải kết quả EDA (dict) thành insight tiếng Việt.

    hypotheses: list[str] — giả thuyết cần đánh giá. Nếu có, thêm section kiểm chứng vào cuối.
    charts: list[dict] — chart đã chạy (cả 'trigger' và 'planner'); chỉ chart 'planner' được
        liệt kê cho LLM gắn thẻ [[chart:ID]] ngay trong bài viết.
    """
    prompt = INSIGHT_USER.format(
        analysis_results=_serialize(eda_results),
        domain_context=domain_context or DOMAIN_GENERIC,
        available_charts=_format_chart_list(charts),
    )

    if hypotheses:
        hyp_lines = "\n".join(f"H{i+1}: {h}" for i, h in enumerate(hypotheses))
        prompt += f"""

---
Ngoài 4 section trên, hãy thêm section 5:

**5. Kiểm chứng giả thuyết**
{hyp_lines}

Với mỗi giả thuyết, viết 2-3 câu bằng tiếng Việt tự nhiên: kết luận + GIẢI THÍCH TẠI SAO.
KHÔNG giữ tên biến tiếng Anh/snake_case, KHÔNG dùng ký hiệu kiểu code ("r=-0.04",
"p_value=0.03") — dịch tên cột sang tiếng Việt và viết số liệu thành câu văn bình thường
trong ngoặc (vd thay vì "r=-0.04" hãy viết "mức tương quan rất yếu, gần như không đáng kể"):
- ✅ XÁC NHẬN — giải thích vì sao số liệu cho thấy điều này đúng, ý nghĩa thực tế là gì,
  điều này có hợp lý theo domain/logic thông thường không
- ❌ BÁC BỎ — giải thích vì sao số liệu KHÔNG ủng hộ giả thuyết, và nếu có thể, suy đoán
  lý do thực sự đằng sau (vd có biến khác chi phối, hoặc giả thuyết ban đầu sai hướng)
- ⚠️ KHÔNG ĐỦ DỮ LIỆU — chỉ rõ THIẾU loại phân tích/cột nào để kiểm chứng được (vd "cần
  so sánh điểm đánh giá của khách giữa nhóm có trả hàng và không trả hàng, nhưng bước này
  chưa được thực hiện"), không chỉ nói chung là "không có dữ liệu"
"""

    return call_llm(prompt, system=INSIGHT_SYSTEM, model=MODEL_DEFAULT)
