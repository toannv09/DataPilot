"""Sinh biểu đồ EDA bằng matplotlib/seaborn. Tất cả hàm save PNG vào outputs/charts/, trả về path."""

import matplotlib
matplotlib.use("Agg")

import os
import uuid

import matplotlib.pyplot as plt
import seaborn as sns

from tools.stats_engine import hourly_pattern, weekly_pattern, monthly_pattern, time_series_decompose

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "charts")


def _save(fig, name):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{name}_{uuid.uuid4().hex[:8]}.png")
    fig.savefig(path, bbox_inches="tight", dpi=100)
    plt.close(fig)
    return path


def plot_distribution(df, col):
    """Histogram + KDE của một cột."""
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.histplot(df[col].dropna(), kde=True, ax=ax)
    ax.set_title(f"Phân phối của {col}")
    ax.set_xlabel(col)
    return _save(fig, f"dist_{col}")


def plot_heatmap(df, cols):
    """Correlation heatmap giữa các cột."""
    fig, ax = plt.subplots(figsize=(8, 6))
    corr = df[cols].corr(method="pearson")
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
    ax.set_title("Ma trận tương quan")
    return _save(fig, "heatmap")


def plot_time_series(df, col, resample=None):
    """Line chart theo thời gian, có thể resample (vd: '1D')."""
    series = df[col]
    if resample:
        series = series.resample(resample).mean()

    fig, ax = plt.subplots(figsize=(12, 5))
    series.plot(ax=ax)
    ax.set_title(f"Biến động {col} theo thời gian")
    ax.set_xlabel("Thời gian")
    ax.set_ylabel(col)
    return _save(fig, f"timeseries_{col}")


def plot_boxplot(df, col):
    """Boxplot phát hiện outlier."""
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.boxplot(y=df[col].dropna(), ax=ax)
    ax.set_title(f"Boxplot {col}")
    return _save(fig, f"boxplot_{col}")


def plot_seasonal_pattern(df, col, by):
    """Pattern theo giờ ('hour'), ngày trong tuần ('day_of_week') hoặc tháng ('month')."""
    if by == "hour":
        data = hourly_pattern(df, col)
        x_col, title = "hour", "Pattern theo giờ trong ngày"
    elif by == "day_of_week":
        data = weekly_pattern(df, col)
        x_col, title = "day_of_week", "Pattern theo ngày trong tuần"
    elif by == "month":
        data = monthly_pattern(df, col)
        x_col, title = "month", "Pattern theo tháng"
    else:
        raise ValueError(f"by không hợp lệ: {by}")

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=data, x=x_col, y=col, ax=ax)
    ax.set_title(f"{title} — {col}")
    return _save(fig, f"seasonal_{by}_{col}")


def plot_missing_heatmap(df):
    """Heatmap missing value."""
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(df.isna(), cbar=False, yticklabels=False, ax=ax)
    ax.set_title("Bản đồ giá trị thiếu (missing value)")
    return _save(fig, "missing_heatmap")


def plot_decomposition(df, col, period=24):
    """Biểu đồ trend + seasonality + residual."""
    decomposition = time_series_decompose(df, col, period)

    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(list(decomposition["trend"].keys()), list(decomposition["trend"].values()))
    axes[0].set_title(f"Trend — {col}")
    axes[1].plot(list(decomposition["seasonal"].keys()), list(decomposition["seasonal"].values()))
    axes[1].set_title("Seasonality")
    axes[2].plot(list(decomposition["residual"].keys()), list(decomposition["residual"].values()))
    axes[2].set_title("Residual")
    fig.tight_layout()
    return _save(fig, f"decompose_{col}")


def plot_scatter(df, col1, col2):
    """Scatter plot + regression line giữa 2 cột số."""
    sub = df[[col1, col2]].dropna()
    # Sample nếu quá lớn để render nhanh
    if len(sub) > 5000:
        sub = sub.sample(5000, random_state=42)
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.regplot(data=sub, x=col1, y=col2, ax=ax, scatter_kws={"alpha": 0.4, "s": 20})
    ax.set_title(f"{col1} vs {col2}")
    return _save(fig, f"scatter_{col1}_{col2}")


def plot_violin(df, col):
    """Violin plot — thấy cả shape phân phối lẫn outlier."""
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.violinplot(y=df[col].dropna(), ax=ax)
    ax.set_title(f"Violin — {col}")
    return _save(fig, f"violin_{col}")


def plot_boxplot_by(df, col, by):
    """Boxplot nhóm: so sánh phân phối col theo từng giá trị của cột categorical by."""
    sub = df[[col, by]].dropna()
    n_groups = sub[by].nunique()
    fig_w = max(6, n_groups * 1.2)
    fig, ax = plt.subplots(figsize=(fig_w, 5))
    order = sub.groupby(by)[col].median().sort_values(ascending=False).index.tolist()
    sns.boxplot(data=sub, x=by, y=col, order=order, ax=ax)
    ax.set_title(f"{col} theo {by}")
    ax.tick_params(axis="x", rotation=30)
    return _save(fig, f"boxplot_by_{col}_{by}")


def plot_pairplot(df, cols):
    """Scatter matrix — nhìn đồng thời quan hệ giữa nhiều cột số (multivariate)."""
    sub = df[cols].dropna()
    if len(sub) > 2000:
        sub = sub.sample(2000, random_state=42)
    g = sns.pairplot(sub, diag_kind="kde", plot_kws={"alpha": 0.4, "s": 15})
    g.fig.suptitle("Quan hệ đồng thời giữa các biến", y=1.02)
    return _save(g.fig, "pairplot")


def plot_mi_scores(df, target_col):
    """Bar chart MI score ranking — feature nào quan trọng nhất với target."""
    from tools.relationship import mutual_info_scores

    scores = mutual_info_scores(df, target_col)
    if not scores:
        raise ValueError(f"Không tính được MI score cho target '{target_col}'")

    cols = list(scores.keys())
    vals = list(scores.values())
    fig, ax = plt.subplots(figsize=(8, max(4, len(cols) * 0.45)))
    colors = sns.color_palette("Blues_r", len(cols))
    ax.barh(cols[::-1], vals[::-1], color=colors)
    ax.set_title(f"Mutual Information với target: {target_col}")
    ax.set_xlabel("MI Score")
    return _save(fig, f"mi_{target_col}")


def plot_lag_correlation(df, col1, col2, max_lag=24):
    """Biểu đồ tương quan theo độ trễ giữa col1 và col2."""
    from tools.stats_engine import lag_correlation

    result = lag_correlation(df, col1, col2, max_lag)
    lags = list(result["correlations"].keys())
    corrs = list(result["correlations"].values())

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(lags, corrs)
    ax.set_title(f"Lag correlation: {col1} vs {col2}")
    ax.set_xlabel("Lag")
    ax.set_ylabel("Correlation")
    return _save(fig, f"lagcorr_{col1}_{col2}")
