"""LLM quyết định cấu hình xử lý dữ liệu (fill/outlier/encode/scale method) theo user_query."""

import json
import re

from llm.client import MODEL_8B, call_llm
from llm.prompts.preprocessing_prompt import PREPROCESSING_PLANNER_SYSTEM, PREPROCESSING_PLANNER_USER

DEFAULT_PLAN = {
    "fill_method": "median",
    "skip_outlier": False,
    "outlier_method": "iqr",
    "skip_encode": False,
    "skip_scale": False,
    "scale_method": "standard",
    "reason": "Cấu hình mặc định (không có yêu cầu cụ thể).",
}


def plan(user_query, quality_summary):
    """Trả về dict cấu hình xử lý. Query rỗng/generic -> DEFAULT_PLAN, không tốn LLM call."""
    if not user_query or not user_query.strip():
        return dict(DEFAULT_PLAN)

    prompt = PREPROCESSING_PLANNER_USER.format(
        user_query=user_query,
        quality_summary=quality_summary,
    )
    try:
        response = call_llm(prompt, system=PREPROCESSING_PLANNER_SYSTEM, model=MODEL_8B)
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            result = dict(DEFAULT_PLAN)
            result.update(json.loads(match.group(0)))
            return result
    except Exception:
        pass
    return dict(DEFAULT_PLAN)
