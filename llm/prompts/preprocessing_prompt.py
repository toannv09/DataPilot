"""Prompt cho Preprocessing Planner — LLM quyết định bước nào làm, bỏ bước nào, dùng method nào theo user_query."""

PREPROCESSING_PLANNER_SYSTEM = """
Bạn là data engineer. Dựa vào yêu cầu của người dùng và thông tin chất lượng dữ liệu,
hãy quyết định cách xử lý dữ liệu phù hợp. Chỉ trả về JSON hợp lệ, không giải thích thêm.
"""

PREPROCESSING_PLANNER_USER = """
Yêu cầu của người dùng: {user_query}

Thông tin dữ liệu:
{quality_summary}

Quyết định cấu hình xử lý dữ liệu. Các lựa chọn hợp lệ:
- fill_method: "median" (mặc định, robust với outlier) hoặc "mean"
- skip_outlier: true/false — true nếu user yêu cầu giữ nguyên outlier / không xử lý outlier
- outlier_method: "iqr" (mặc định) hoặc "zscore"
- skip_encode: true/false — true nếu user yêu cầu giữ nguyên cột phân loại dạng chữ
- skip_scale: true/false — true nếu user yêu cầu giữ nguyên thang đo gốc (vd để dễ đọc số liệu thật)
- scale_method: "standard" (mặc định, z-score) hoặc "minmax" (đưa về khoảng 0-1)

Nếu user không đề cập gì cụ thể về 1 mục, dùng giá trị mặc định cho mục đó.

Chỉ trả về JSON:
{{
  "fill_method": "median",
  "skip_outlier": false,
  "outlier_method": "iqr",
  "skip_encode": false,
  "skip_scale": false,
  "scale_method": "standard",
  "reason": "Lý do ngắn gọn theo yêu cầu user"
}}
"""
