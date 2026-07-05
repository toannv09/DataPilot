"""LLM lập kế hoạch tool calls theo câu hỏi của user."""

import json
import re

from llm.client import MODEL_DEFAULT, call_llm
from llm.prompts.planner_prompt import PLANNER_SYSTEM, PLANNER_USER


def _extract_json(text):
    """Bỏ markdown code fence (nếu có) rồi parse JSON."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def plan(user_query, file_info, domain_context="", available_columns=None,
         has_datetime_index=False, phase1_summary=""):
    """Trả về dict {"steps": [...], "explanation": "..."}."""
    cols_str = ", ".join(available_columns) if available_columns else "Không rõ — hãy dùng tên cột từ file_info"
    datetime_note = (
        "CÓ DatetimeIndex — dataset đã được set index theo thời gian. "
        "Bắt buộc có ít nhất 1 trong các bước: time_series_decompose, hourly_pattern, weekly_pattern, monthly_pattern, plot_time_series."
        if has_datetime_index else
        "KHÔNG có DatetimeIndex — đây là dữ liệu bảng thông thường, không cần bước time series."
    )
    prompt = PLANNER_USER.format(
        user_query=user_query or "Phân tích tổng quan dữ liệu",
        file_info=file_info,
        domain_context=domain_context or "(không có)",
        available_columns=cols_str,
        datetime_note=datetime_note,
        phase1_summary=phase1_summary or "(chưa có — lập kế hoạch từ đầu)",
    )

    response = call_llm(prompt, system=PLANNER_SYSTEM, model=MODEL_DEFAULT, temperature=0)

    try:
        return _extract_json(response)
    except (json.JSONDecodeError, AttributeError):
        response = call_llm(prompt, system=PLANNER_SYSTEM, model=MODEL_DEFAULT, use_cache=False, temperature=0)
        try:
            return _extract_json(response)
        except (json.JSONDecodeError, AttributeError):
            return {"steps": [], "explanation": "Không thể parse kế hoạch từ LLM."}
