"""Resample, merge nhiều file theo MergePlan và validate kết quả."""

import re

import pandas as pd

# pandas >= 2.2 đổi tên 1 số alias tần suất (vd 'M' -> 'ME', 'H' -> 'h') và cảnh báo
# FutureWarning với tên cũ — LLM (schema_analyzer/eda_planner) vẫn có thể sinh ra tên cũ, nên
# chuẩn hóa lại ở đây thay vì bắt LLM phải biết tên mới.
_DEPRECATED_FREQ_ALIASES = {
    "M": "ME", "Q": "QE", "Y": "YE", "A": "YE", "BM": "BME", "BQ": "BQE", "BA": "BYE",
    "H": "h", "T": "min", "S": "s", "L": "ms", "U": "us", "N": "ns",
}


def normalize_freq(freq):
    """Map alias tần suất cũ (đã deprecated) sang tên mới — giữ nguyên phần số/prefix (vd '2M' -> '2ME')."""
    if not isinstance(freq, str):
        return freq
    match = re.fullmatch(r"(\d*)([A-Za-z]+)", freq.strip())
    if not match:
        return freq
    count, alias = match.groups()
    return f"{count}{_DEPRECATED_FREQ_ALIASES.get(alias, alias)}"


def resample_to_frequency(df, col, freq):
    """Resample time series về tần suất mới (vd '1H', '1D'). Numeric -> mean, khác -> first."""
    df = df.copy()
    df[col] = pd.to_datetime(df[col])
    df = df.set_index(col)

    numeric_cols = df.select_dtypes(include="number").columns
    other_cols = df.columns.difference(numeric_cols)

    agg = {c: "mean" for c in numeric_cols}
    agg.update({c: "first" for c in other_cols})

    resampled = df.resample(normalize_freq(freq)).agg(agg)
    return resampled.reset_index()


def merge_files(files, merge_plan):
    """Merge các file theo MergePlan (từ schema_analyzer.suggest_merge_plan).

    files: dict[str, DataFrame]
    merge_plan: MergePlan
    """
    if not merge_plan.can_merge or not merge_plan.groups:
        raise ValueError("Merge plan không có nhóm nào để merge")

    base_name = merge_plan.groups[0]["file_a"]
    result = files[base_name].copy()
    merged_names = {base_name}

    for group in merge_plan.groups:
        if group["file_a"] in merged_names and group["file_b"] in merged_names:
            continue
        if group["file_a"] in merged_names:
            other_name = group["file_b"]
            col_left, col_right = group["join_col_a"], group["join_col_b"]
        elif group["file_b"] in merged_names:
            other_name = group["file_a"]
            col_left, col_right = group["join_col_b"], group["join_col_a"]
        else:
            continue

        other_df = files[other_name].copy()

        if group["type"] == "datetime":
            result[col_left] = pd.to_datetime(result[col_left])
            other_df[col_right] = pd.to_datetime(other_df[col_right])

            if group["need_resample"] and group["target_freq"]:
                result = resample_to_frequency(result, col_left, group["target_freq"])
                other_df = resample_to_frequency(other_df, col_right, group["target_freq"])

        result = result.merge(
            other_df,
            left_on=col_left,
            right_on=col_right,
            how="left",
            suffixes=("", f"_{other_name}"),
        )
        merged_names.add(other_name)

    return result


def validate_merge_result(df, original_files):
    """Kiểm tra kết quả merge có hợp lý không.

    original_files: dict[str, DataFrame]
    """
    n_rows = len(df)
    original_row_counts = {name: len(orig_df) for name, orig_df in original_files.items()}
    max_orig = max(original_row_counts.values()) if original_row_counts else 0

    warnings = []
    if max_orig and n_rows < 0.5 * max_orig:
        warnings.append(
            "Số dòng sau merge giảm hơn 50% so với file gốc lớn nhất, "
            "có thể join key không khớp tốt."
        )

    null_ratio = df.isna().mean()
    high_null_cols = null_ratio[null_ratio > 0.5].index.tolist()
    if high_null_cols:
        warnings.append(f"Các cột sau có >50% giá trị thiếu sau merge: {high_null_cols}")

    return {
        "n_rows_merged": n_rows,
        "n_cols_merged": len(df.columns),
        "original_row_counts": original_row_counts,
        "warnings": warnings,
        "is_valid": len(warnings) == 0,
    }


def add_holiday_feature(df, holiday_df, time_col):
    """Thêm cột is_holiday (0/1) dựa trên cột 'date' của holiday_df."""
    df = df.copy()
    holiday_dates = set(pd.to_datetime(holiday_df["date"]).dt.date)
    df["is_holiday"] = pd.to_datetime(df[time_col]).dt.date.isin(holiday_dates).astype(int)
    return df
