# Tool library

Tất cả tool viết sẵn trong `tools/`. LLM gọi tool theo tên hàm + tham số, không cần sinh lại code.

> **Nguyên tắc:** Bước chuẩn → gọi tool (tiết kiệm token, ít lỗi). Yêu cầu custom → LLM sinh code tự do.

---

## `schema_analyzer.py`

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `read_schema(file_path)` | path | dict | Tên cột, kiểu dữ liệu, số dòng, sample 5 dòng |
| `detect_datetime_columns(df)` | DataFrame | list[str] | Danh sách cột thời gian |
| `detect_time_frequency(df, col)` | DataFrame, str | str | Tần suất: "30min", "1H", "1D" |
| `find_join_candidates(files)` | list[DataFrame] | list[dict] | Cặp cột có thể join giữa các file |
| `suggest_merge_plan(files)` | list[DataFrame] | MergePlan | Đề xuất cách merge kèm lý do tiếng Việt |

---

## `quality_checker.py`

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `check_missing(df)` | DataFrame | dict | Tỷ lệ null từng cột, pattern missing |
| `check_duplicates(df)` | DataFrame | dict | Số dòng trùng, vị trí |
| `check_outliers_iqr(df, col)` | DataFrame, str | dict | Outlier theo IQR, ngưỡng Q1/Q3 |
| `check_outliers_rolling(df, col, window=24)` | DataFrame, str, int | dict | Outlier time series theo rolling mean ± 3std |
| `check_type_mismatch(df)` | DataFrame | dict | Cột số có giá trị chữ lẫn vào |
| `check_value_range(df, col, min_val, max_val)` | DataFrame, str, float, float | dict | Giá trị ngoài range hợp lý |

---

## `stats_engine.py`

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `basic_stats(df, cols)` | DataFrame, list[str] | dict | mean, median, std, min, max, percentiles |
| `correlation_matrix(df, cols)` | DataFrame, list[str] | DataFrame | Ma trận tương quan Pearson |
| `skewness_kurtosis(df, col)` | DataFrame, str | dict | Độ lệch và độ nhọn phân phối |
| `time_series_decompose(df, col, period)` | DataFrame, str, int | dict | Trend, seasonality, residual |
| `lag_correlation(df, col1, col2, max_lag)` | DataFrame, str, str, int | dict | Tương quan trễ giữa 2 chuỗi |
| `cross_file_correlation(df, col1, col2)` | DataFrame, str, str | float | Tương quan sau khi merge |
| `hourly_pattern(df, col)` | DataFrame, str | DataFrame | Trung bình theo giờ trong ngày |
| `weekly_pattern(df, col)` | DataFrame, str | DataFrame | Trung bình theo ngày trong tuần |
| `monthly_pattern(df, col)` | DataFrame, str | DataFrame | Trung bình theo tháng |

---

## `viz_engine.py`

> Tất cả hàm save PNG vào `outputs/charts/`, trả về đường dẫn file.

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `plot_distribution(df, col)` | DataFrame, str | str (path) | Histogram + KDE |
| `plot_heatmap(df, cols)` | DataFrame, list[str] | str (path) | Correlation heatmap |
| `plot_time_series(df, col, resample)` | DataFrame, str, str | str (path) | Line chart theo thời gian |
| `plot_boxplot(df, col)` | DataFrame, str | str (path) | Boxplot outlier |
| `plot_seasonal_pattern(df, col, by)` | DataFrame, str, str | str (path) | Pattern theo giờ/ngày/tháng |
| `plot_missing_heatmap(df)` | DataFrame | str (path) | Heatmap missing value |
| `plot_decomposition(df, col)` | DataFrame, str | str (path) | Trend + seasonality + residual |
| `plot_lag_correlation(df, col1, col2)` | DataFrame, str, str | str (path) | Lag correlation chart |

---

## `file_merger.py`

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `resample_to_frequency(df, col, freq)` | DataFrame, str, str | DataFrame | Resample time series về tần suất mới |
| `merge_files(files, merge_plan)` | list[DataFrame], MergePlan | DataFrame | Merge theo plan |
| `validate_merge_result(df, original_files)` | DataFrame, list | dict | Kiểm tra kết quả merge hợp lý |
| `add_holiday_feature(df, holiday_df, time_col)` | DataFrame, DataFrame, str | DataFrame | Thêm cột is_holiday |

---

## `tools/ml/preprocessor.py`

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `handle_missing(df, col, strategy)` | DataFrame, str, str | DataFrame | fill median/mean/drop/forward_fill |
| `encode_categorical(df, col, method)` | DataFrame, str, str | DataFrame | label hoặc onehot tùy cardinality |
| `scale_features(df, cols, method)` | DataFrame, list, str | DataFrame, Scaler | standard hoặc minmax |
| `create_time_features(df, col)` | DataFrame, str | DataFrame | Thêm: hour, day_of_week, month, is_weekend, is_holiday |
| `train_test_split_time(df, target, ratio)` | DataFrame, str, float | tuple | Split theo thời gian, không random |
| `train_test_split_random(df, target, ratio)` | DataFrame, str, float | tuple | Split random cho non-time-series |

---

## `tools/ml/model_selector.py`

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `detect_task_type(df, target_col)` | DataFrame, str | str | "regression" / "classification" / "clustering" |
| `get_baseline_models(task_type)` | str | list | Danh sách model phù hợp |
| `suggest_models_by_llm(task_desc, eda_insights)` | str, str | list | LLM gợi ý model theo context domain |

**Baseline models theo task:**
- Regression: `LinearRegression`, `RandomForestRegressor`, `XGBRegressor`
- Classification: `LogisticRegression`, `RandomForestClassifier`, `XGBClassifier`
- Clustering: `KMeans`, `DBSCAN`

---

## `tools/ml/trainer.py`

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `train_and_evaluate(X_train, y_train, X_test, y_test, models)` | arrays, list | dict | Train tất cả model, trả metrics |
| `cross_validate_model(model, X, y, cv)` | model, arrays, int | dict | Cross-validate, trả mean ± std |
| `compare_models(results)` | dict | DataFrame | Leaderboard so sánh các model |
| `get_best_model(results, metric)` | dict, str | model | Model tốt nhất theo metric |
| `save_model(model, name)` | model, str | str | Lưu vào `outputs/models/`, trả path |

**Metric tự động theo task:**
- Regression: RMSE, MAE, R²
- Classification: Accuracy, F1, Precision, Recall
- Clustering: Silhouette score, Inertia

---

## `tools/ml/ml_viz.py`

> Tất cả hàm save PNG vào `outputs/ml_charts/`, trả về đường dẫn file.

| Hàm | Input | Output | Mô tả |
|-----|-------|--------|-------|
| `plot_confusion_matrix(y_true, y_pred, labels)` | arrays, list | str (path) | Confusion matrix |
| `plot_feature_importance(model, feature_names)` | model, list | str (path) | Feature importance bar chart |
| `plot_actual_vs_predicted(y_true, y_pred)` | arrays | str (path) | Actual vs predicted scatter |
| `plot_residuals(y_true, y_pred)` | arrays | str (path) | Residual plot |
| `plot_model_comparison(leaderboard)` | DataFrame | str (path) | Bar chart so sánh các model |