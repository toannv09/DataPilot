"""Detect schema, join key giữa các file và đề xuất merge plan bằng tiếng Việt."""

import json

from llm.client import MODEL_8B, call_llm
from tools.schema_analyzer import find_join_candidates, read_schema, suggest_merge_plan

MERGE_SUGGESTION_USER = """
Các file đã upload:
{files_info}

Phát hiện các cột có thể join:
{join_candidates}

Hãy đề xuất cách kết hợp các file này bằng tiếng Việt, giải thích:
1. Nên join file nào với file nào
2. Theo cột nào
3. Có cần resample không và tại sao
4. Kết quả sau merge sẽ có thông tin gì

Viết ngắn gọn, dễ hiểu với người không biết kỹ thuật.
"""


def detect(files, file_paths=None):
    """Đọc schema, tìm join candidates và đề xuất merge plan.

    files: dict[str, DataFrame]
    file_paths: dict[str, str] (optional) — nếu có, đọc schema chi tiết từ file gốc.
    """
    if file_paths:
        schemas = {name: read_schema(path) for name, path in file_paths.items()}
    else:
        schemas = {
            name: {
                "n_rows": len(df),
                "n_cols": len(df.columns),
                "columns": {col: str(df[col].dtype) for col in df.columns},
            }
            for name, df in files.items()
        }

    join_candidates = find_join_candidates(files)
    merge_plan = suggest_merge_plan(files)

    suggestion = None
    if len(files) > 1 and join_candidates:
        prompt = MERGE_SUGGESTION_USER.format(
            files_info=json.dumps(schemas, ensure_ascii=False, default=str),
            join_candidates=json.dumps(join_candidates, ensure_ascii=False, default=str),
        )
        suggestion = call_llm(prompt, model=MODEL_8B)

    return {
        "schemas": schemas,
        "join_candidates": join_candidates,
        "merge_plan": merge_plan,
        "suggestion": suggestion,
    }
