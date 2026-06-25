"""Kiểm tra chất lượng dữ liệu: missing value, duplicate, outlier, type mismatch, value range."""

import pandas as pd


def check_missing(df):
    """Tỷ lệ null từng cột và pattern missing."""
    n_rows = len(df)
    missing_count = df.isna().sum()
    missing_ratio = (missing_count / n_rows).round(4) if n_rows else missing_count * 0.0

    columns = {
        col: {
            "missing_count": int(missing_count[col]),
            "missing_ratio": float(missing_ratio[col]),
        }
        for col in df.columns
    }

    cols_with_missing = [col for col, info in columns.items() if info["missing_count"] > 0]

    return {
        "n_rows": n_rows,
        "columns": columns,
        "cols_with_missing": cols_with_missing,
        "total_missing": int(missing_count.sum()),
    }


def check_duplicates(df):
    """Số dòng trùng và vị trí (index)."""
    duplicated = df.duplicated(keep="first")
    return {
        "n_duplicates": int(duplicated.sum()),
        "duplicate_indices": df.index[duplicated].tolist(),
    }


def check_outliers_iqr(df, col):
    """Outlier theo IQR (Q1 - 1.5*IQR, Q3 + 1.5*IQR)."""
    series = df[col].dropna()
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outliers = series[(series < lower) | (series > upper)]

    return {
        "col": col,
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(iqr),
        "lower_bound": float(lower),
        "upper_bound": float(upper),
        "n_outliers": int(outliers.shape[0]),
        "outlier_indices": outliers.index.tolist(),
    }


def check_outliers_rolling(df, col, window=24):
    """Outlier time series theo rolling mean ± 3*std."""
    series = df[col]
    rolling_mean = series.rolling(window=window, min_periods=1, center=True).mean()
    rolling_std = series.rolling(window=window, min_periods=1, center=True).std().fillna(0)

    lower = rolling_mean - 3 * rolling_std
    upper = rolling_mean + 3 * rolling_std

    outlier_mask = (series < lower) | (series > upper)
    outliers = series[outlier_mask]

    return {
        "col": col,
        "window": window,
        "n_outliers": int(outliers.shape[0]),
        "outlier_indices": outliers.index.tolist(),
    }


def check_type_mismatch(df):
    """Phát hiện cột số nhưng có giá trị chữ (object) lẫn vào."""
    mismatches = {}
    for col in df.columns:
        if df[col].dtype != object:
            continue

        non_null = df[col].dropna()
        if non_null.empty:
            continue

        numeric = pd.to_numeric(non_null, errors="coerce")
        n_numeric = numeric.notna().sum()
        n_non_numeric = numeric.isna().sum()

        # Cột chủ yếu là số nhưng có vài giá trị không parse được -> mismatch
        if n_numeric > 0 and n_non_numeric > 0 and n_numeric / len(non_null) > 0.5:
            bad_values = non_null[numeric.isna()].unique().tolist()
            mismatches[col] = {
                "n_numeric": int(n_numeric),
                "n_non_numeric": int(n_non_numeric),
                "bad_values": bad_values[:20],
            }

    return {"mismatches": mismatches}


def check_value_range(df, col, min_val, max_val):
    """Giá trị nằm ngoài khoảng [min_val, max_val] hợp lý."""
    series = df[col]
    out_of_range = series[(series < min_val) | (series > max_val)]

    return {
        "col": col,
        "min_val": min_val,
        "max_val": max_val,
        "n_out_of_range": int(out_of_range.shape[0]),
        "out_of_range_indices": out_of_range.index.tolist(),
    }
