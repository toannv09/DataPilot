"""Sinh hypothesis phân tích từ domain context + schema, trả về list giả thuyết để EDA kiểm chứng."""

import json
import re

from llm.client import MODEL_LITE, call_llm

HYPOTHESIS_SYSTEM = """
Bạn là data analyst. Dựa trên thông tin domain và schema dataset,
hãy sinh 2–3 giả thuyết có thể kiểm chứng bằng dữ liệu.
Chỉ trả về JSON hợp lệ.
"""

HYPOTHESIS_USER = """
Domain/nghiệp vụ:
{domain_context}

Schema dataset:
{schemas}

Câu hỏi/yêu cầu của user (nếu có, ưu tiên sinh giả thuyết liên quan đến chủ đề này): {user_query}
{profiling_hint}
Sinh 2–3 giả thuyết cụ thể và có thể kiểm chứng bằng thống kê hoặc biểu đồ.

CHỈ sinh giả thuyết test được bằng 1 trong 2 cách sau (vì hệ thống chỉ có 2 loại tool kiểm định):
1. So sánh 1 cột số giữa các nhóm của 1 cột categorical CÓ SẴN trong schema
   (vd department, region, category — KHÔNG phải cột số được chia ngưỡng)
2. Tương quan giữa 2 cột số có sẵn trong schema

Mỗi giả thuyết phải:
- Đề cập đúng tên cột trong schema
- Có thể xác nhận hoặc bác bỏ từ dữ liệu

KHÔNG được sinh giả thuyết dạng:
- "X cao hơn trung bình của X" hoặc "nhóm có X > mean(X)" (chia nhóm theo ngưỡng/percentile của cột số — KHÔNG có tool hỗ trợ)
- "Top 25%/most/least theo cột số" (không có tool tạo nhóm động kiểu này)
- Quá rộng ("phân tích dữ liệu" không phải là giả thuyết)

Ví dụ tốt: "Lương trung bình của nhóm Engineering cao hơn Sales ít nhất 20%" (so sánh theo department — cột categorical có sẵn)
Ví dụ tốt: "training_hours tương quan dương với performance_score" (tương quan 2 cột số)
Ví dụ KHÔNG tốt: "Nhân viên có training_hours > trung bình có performance_score cao hơn 10%" (cần chia nhóm theo ngưỡng — không test được)

Chỉ trả về JSON:
{{
  "hypotheses": [
    "giả thuyết 1",
    "giả thuyết 2"
  ]
}}
"""

HYPOTHESIS_EVAL_PROMPT = """
Các giả thuyết cần đánh giá:
{hypotheses}

Kết quả phân tích:
{analysis_results}

Với mỗi giả thuyết, kết luận dựa trên số liệu từ kết quả phân tích:
- XÁC NHẬN: nếu số liệu ủng hộ giả thuyết (kèm số liệu cụ thể)
- BÁC BỎ: nếu số liệu mâu thuẫn với giả thuyết (kèm số liệu cụ thể)
- KHÔNG ĐỦ DỮ LIỆU: nếu không tìm thấy bằng chứng trong kết quả

Trả về dạng markdown, mỗi giả thuyết 1–2 câu.
"""


def generate_hypotheses(schemas, domain_context="", user_query="", profiling_context=""):
    """Sinh 2–3 giả thuyết từ domain + schema (+ user_query, profiling_context nếu có). Trả về list string."""
    # Chỉ sinh hypothesis khi có domain thực sự, không dùng cho DOMAIN_GENERIC
    if not domain_context or len(domain_context.strip()) < 30:
        return []
    # Không sinh nếu domain là DOMAIN_GENERIC (bắt đầu bằng "Không có thông tin domain")
    if domain_context.strip().startswith("Không có thông tin domain"):
        return []

    schemas_str = json.dumps(schemas, ensure_ascii=False, default=str)[:2000]
    profiling_hint = (
        f"Phát hiện từ profiling (ưu tiên sinh giả thuyết kiểm chứng các điểm này):\n{profiling_context}\n"
        if profiling_context else ""
    )
    prompt = HYPOTHESIS_USER.format(
        domain_context=domain_context.strip(),
        schemas=schemas_str,
        user_query=user_query or "(không có)",
        profiling_hint=profiling_hint,
    )
    try:
        response = call_llm(prompt, system=HYPOTHESIS_SYSTEM, model=MODEL_LITE)
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return data.get("hypotheses", [])
    except Exception:
        pass
    return []


def evaluate_hypotheses(hypotheses, analysis_results):
    """Tạo prompt để insight_generator đánh giá từng giả thuyết."""
    if not hypotheses:
        return ""
    import json as _json
    results_str = _json.dumps(analysis_results, ensure_ascii=False, default=str)[:5000]
    return HYPOTHESIS_EVAL_PROMPT.format(
        hypotheses="\n".join(f"H{i+1}: {h}" for i, h in enumerate(hypotheses)),
        analysis_results=results_str,
    )
