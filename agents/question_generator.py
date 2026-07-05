"""Tự động sinh câu hỏi phân tích từ schema dataset trước khi lên kế hoạch EDA."""

import json
import re

from llm.client import MODEL_LITE, call_llm

QUESTION_GEN_SYSTEM = """
Bạn là data analyst. Nhìn vào schema dataset, sinh ra các câu hỏi phân tích
cụ thể và phù hợp nhất để hiểu dữ liệu này. Chỉ trả về JSON hợp lệ.
"""

QUESTION_GEN_USER = """
Schema dataset:
{schemas}

Câu hỏi gốc của user (có thể rỗng): {user_query}
Dataset có DatetimeIndex: {has_datetime}
Domain (nếu có): {domain_context}
{profiling_hint}
Dựa vào schema, sinh 3–5 câu hỏi phân tích cụ thể.
Ưu tiên câu hỏi về: chất lượng dữ liệu, phân phối, tương quan, outlier, nhóm/phân khúc.
{datetime_instruction}

KHÔNG được sinh câu hỏi về xu hướng thời gian, time series, pattern theo giờ/ngày/tháng nếu DatetimeIndex = Không.

Chỉ trả về JSON:
{{
  "questions": ["câu hỏi 1", "câu hỏi 2", "câu hỏi 3"],
  "focus": "1 câu tóm tắt trọng tâm phân tích"
}}
"""


def generate_questions(schemas, user_query="", domain_context="", has_datetime=False,
                       profiling_context=""):
    """Sinh 3–5 câu hỏi phân tích từ schema. Trả về dict với keys 'questions' và 'focus'."""
    schemas_str = json.dumps(schemas, ensure_ascii=False, default=str)[:3000]
    dt_instruction = (
        "Dataset CÓ DatetimeIndex: được phép sinh câu hỏi về trend, pattern theo giờ/ngày/tháng."
        if has_datetime else
        "Dataset KHÔNG có DatetimeIndex: tuyệt đối không sinh câu hỏi liên quan đến thời gian."
    )
    profiling_hint = (
        f"Phát hiện từ profiling (ưu tiên câu hỏi về các điểm này):\n{profiling_context}\n"
        if profiling_context else ""
    )
    prompt = QUESTION_GEN_USER.format(
        schemas=schemas_str,
        user_query=user_query or "(không có)",
        has_datetime="Có" if has_datetime else "Không",
        domain_context=domain_context or "(không có)",
        datetime_instruction=dt_instruction,
        profiling_hint=profiling_hint,
    )
    try:
        response = call_llm(prompt, system=QUESTION_GEN_SYSTEM, model=MODEL_LITE)
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return {"questions": [], "focus": ""}
