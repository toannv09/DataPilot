"""Thống kê mô tả, correlation, seasonality cho dữ liệu time series.

Lưu ý: các hàm pattern theo thời gian (hourly/weekly/monthly) và
time_series_decompose / lag_correlation yêu cầu df có DatetimeIndex.
"""

import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose


def basic_stats(df, cols):
    """mean, median, std, min, max, percentiles cho từng cột."""
    result = {}
    for col in cols:
        series = df[col].dropna()
        result[col] = {
            "mean": float(series.mean()),
            "median": float(series.median()),
            "std": float(series.std()),
            "min": float(series.min()),
            "max": float(series.max()),
            "p25": float(series.quantile(0.25)),
            "p75": float(series.quantile(0.75)),
            "p95": float(series.quantile(0.95)),
        }
    return result


def correlation_matrix(df, cols):
    """Ma trận tương quan Pearson giữa các cột số."""
    return df[cols].corr(method="pearson")


def spearman_correlation(df, cols):
    """Ma trận tương quan Spearman — robust hơn Pearson khi có outlier hoặc phân phối lệch."""
    return df[cols].corr(method="spearman")


def normality_test(df, col):
    """Kiểm định phân phối chuẩn: Shapiro-Wilk (n<5000) hoặc KS test (n>=5000)."""
    from scipy import stats as sp_stats

    series = df[col].dropna()
    n = len(series)
    if n < 3:
        return {"col": col, "test": "insufficient_data", "p_value": None, "is_normal": None}

    if n < 5000:
        stat, p = sp_stats.shapiro(series.iloc[:5000])
        test_name = "shapiro-wilk"
    else:
        stat, p = sp_stats.kstest(series, "norm", args=(float(series.mean()), float(series.std())))
        test_name = "kolmogorov-smirnov"

    return {
        "col": col,
        "test": test_name,
        "n": n,
        "statistic": round(float(stat), 4),
        "p_value": round(float(p), 4),
        "is_normal": bool(p > 0.05),
        "interpretation": "phân phối chuẩn (p>0.05)" if p > 0.05 else "không phân phối chuẩn (p≤0.05)",
    }


def group_stats(df, col, by):
    """Thống kê mô tả của col theo từng nhóm trong cột categorical by."""
    result = {}
    for group, sub_df in df.groupby(by):
        series = sub_df[col].dropna()
        result[str(group)] = {
            "n": len(series),
            "mean": round(float(series.mean()), 2),
            "median": round(float(series.median()), 2),
            "std": round(float(series.std()), 2),
            "min": round(float(series.min()), 2),
            "max": round(float(series.max()), 2),
        }
    return result


def skewness_kurtosis(df, col):
    """Độ lệch (skewness) và độ nhọn (kurtosis) của phân phối."""
    series = df[col].dropna()
    return {
        "col": col,
        "skewness": float(series.skew()),
        "kurtosis": float(series.kurt()),
    }


def _series_summary(series):
    """Tóm tắt 1 Series thành thống kê cơ bản, tránh trả về toàn bộ dữ liệu."""
    return {
        "mean": float(series.mean()),
        "std": float(series.std()),
        "min": float(series.min()),
        "max": float(series.max()),
    }


def time_series_decompose(df, col, period):
    """Phân rã trend, seasonality, residual của chuỗi thời gian (trả về dạng tóm tắt)."""
    series = df[col].dropna()
    result = seasonal_decompose(series, model="additive", period=period, extrapolate_trend="freq")

    return {
        "col": col,
        "period": period,
        "trend": _series_summary(result.trend.dropna()),
        "seasonal": _series_summary(result.seasonal.dropna()),
        "residual": _series_summary(result.resid.dropna()),
    }


def lag_correlation(df, col1, col2, max_lag):
    """Tương quan giữa col1 và col2 với độ trễ (lag) từ -max_lag đến max_lag."""
    correlations = {}
    for lag in range(-max_lag, max_lag + 1):
        shifted = df[col2].shift(lag)
        corr = df[col1].corr(shifted)
        correlations[lag] = float(corr) if pd.notna(corr) else None

    best_lag = max(
        (lag for lag, corr in correlations.items() if corr is not None),
        key=lambda lag: abs(correlations[lag]),
        default=None,
    )

    return {
        "col1": col1,
        "col2": col2,
        "correlations": correlations,
        "best_lag": best_lag,
        "best_corr": correlations.get(best_lag) if best_lag is not None else None,
    }


def cross_file_correlation(df, col1, col2):
    """Tương quan Pearson giữa 2 cột sau khi đã merge."""
    return float(df[col1].corr(df[col2]))


def hourly_pattern(df, col):
    """Trung bình giá trị `col` theo giờ trong ngày (0-23)."""
    grouped = df.groupby(df.index.hour)[col].mean()
    grouped.index.name = "hour"
    return grouped.reset_index()


def weekly_pattern(df, col):
    """Trung bình giá trị `col` theo ngày trong tuần (0=Thứ 2 .. 6=Chủ nhật)."""
    grouped = df.groupby(df.index.dayofweek)[col].mean()
    grouped.index.name = "day_of_week"
    return grouped.reset_index()


def monthly_pattern(df, col):
    """Trung bình giá trị `col` theo tháng (1-12)."""
    grouped = df.groupby(df.index.month)[col].mean()
    grouped.index.name = "month"
    return grouped.reset_index()
