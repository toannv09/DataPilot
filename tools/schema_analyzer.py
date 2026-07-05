"""Đọc schema file, detect cột thời gian, tần suất, và đề xuất merge plan giữa nhiều file."""

import os
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class MergePlan:
    can_merge: bool
    groups: list = field(default_factory=list)
    reason: str = ""


def read_schema(file_path):
    """Đọc cấu trúc file: tên cột, kiểu dữ liệu, số dòng, sample 5 dòng."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    return {
        "file_name": os.path.basename(file_path),
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": {col: str(df[col].dtype) for col in df.columns},
        "sample": df.head(5).to_dict(orient="records"),
    }


def detect_datetime_columns(df):
    """Trả về danh sách tên cột có thể là cột thời gian.

    Chỉ áp dụng heuristic theo tên cho cột dạng string/object — cột số (int/float)
    bị loại trừ vì pd.to_datetime() có thể "convert thành công" số nguyên nhỏ
    thành timestamp gần epoch (1970), gây false positive (vd "overtime_hours"
    chứa substring "time" nhưng là số giờ làm thêm, không phải ngày giờ).
    """
    datetime_cols = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            datetime_cols.append(col)
            continue

        if pd.api.types.is_numeric_dtype(df[col]):
            continue

        name = col.lower()
        if any(keyword in name for keyword in ["time", "date", "thoi_gian", "ngay"]):
            try:
                pd.to_datetime(df[col].dropna().head(20))
                datetime_cols.append(col)
            except (ValueError, TypeError):
                continue

    return datetime_cols


def detect_time_frequency(df, col):
    """Trả về tần suất thời gian: '30min', '1H', '1D', ..."""
    times = pd.to_datetime(df[col]).dropna().sort_values().unique()
    if len(times) < 2:
        return None

    diffs = pd.Series(times[1:] - times[:-1])
    delta = pd.Timedelta(diffs.mode().iloc[0])
    seconds = delta.total_seconds()

    if seconds % 86400 == 0:
        return f"{int(seconds // 86400)}D"
    if seconds % 3600 == 0:
        return f"{int(seconds // 3600)}H"
    if seconds % 60 == 0:
        return f"{int(seconds // 60)}min"
    return f"{int(seconds)}S"


def find_join_candidates(files):
    """Tìm các cặp cột có thể join giữa các file.

    files: dict[str, DataFrame] — key là tên file.
    Trả về list[dict] mô tả cặp cột join khả thi.
    """
    candidates = []
    file_names = list(files.keys())

    file_meta = {}
    for name, df in files.items():
        dt_cols = detect_datetime_columns(df)
        meta = {
            "datetime_cols": {c: detect_time_frequency(df, c) for c in dt_cols},
            "columns": set(df.columns),
        }
        file_meta[name] = meta

    for i in range(len(file_names)):
        for j in range(i + 1, len(file_names)):
            a, b = file_names[i], file_names[j]

            for col_a, freq_a in file_meta[a]["datetime_cols"].items():
                for col_b, freq_b in file_meta[b]["datetime_cols"].items():
                    candidates.append({
                        "file_a": a,
                        "file_b": b,
                        "col_a": col_a,
                        "col_b": col_b,
                        "type": "datetime",
                        "freq_a": freq_a,
                        "freq_b": freq_b,
                        "same_freq": freq_a == freq_b,
                    })

            common_cols = file_meta[a]["columns"] & file_meta[b]["columns"]
            for col in common_cols:
                if col in file_meta[a]["datetime_cols"]:
                    continue
                candidates.append({
                    "file_a": a,
                    "file_b": b,
                    "col_a": col,
                    "col_b": col,
                    "type": "categorical",
                    "freq_a": None,
                    "freq_b": None,
                    "same_freq": None,
                })

    return candidates


def suggest_merge_plan(files):
    """Đề xuất cách merge các file dựa trên join candidates.

    files: dict[str, DataFrame]
    Trả về MergePlan.
    """
    candidates = find_join_candidates(files)

    if not candidates:
        return MergePlan(
            can_merge=False,
            groups=[],
            reason="Không tìm thấy cột chung giữa các file để kết hợp. Sẽ phân tích riêng từng file.",
        )

    groups = []
    reasons = []
    for cand in candidates:
        if cand["type"] == "datetime":
            group = {
                "file_a": cand["file_a"],
                "file_b": cand["file_b"],
                "join_col_a": cand["col_a"],
                "join_col_b": cand["col_b"],
                "type": "datetime",
                "need_resample": not cand["same_freq"],
                "target_freq": cand["freq_a"] if cand["freq_a"] else cand["freq_b"],
            }
            groups.append(group)
            if cand["same_freq"]:
                reasons.append(
                    f"File {cand['file_a']} và {cand['file_b']} có thể ghép theo cột thời gian "
                    f"('{cand['col_a']}' và '{cand['col_b']}'), cùng tần suất {cand['freq_a']}."
                )
            else:
                reasons.append(
                    f"File {cand['file_a']} ({cand['freq_a']}) và {cand['file_b']} ({cand['freq_b']}) "
                    f"có tần suất khác nhau, cần resample về cùng tần suất trước khi ghép theo "
                    f"'{cand['col_a']}' / '{cand['col_b']}'."
                )
        else:
            groups.append({
                "file_a": cand["file_a"],
                "file_b": cand["file_b"],
                "join_col_a": cand["col_a"],
                "join_col_b": cand["col_b"],
                "type": "categorical",
                "need_resample": False,
                "target_freq": None,
            })
            reasons.append(
                f"File {cand['file_a']} và {cand['file_b']} có thể ghép theo cột '{cand['col_a']}'."
            )

    return MergePlan(can_merge=True, groups=groups, reason=" ".join(reasons))
