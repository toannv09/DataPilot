"""Prompt cho ML agent — xác định task type, gợi ý model, giải thích kết quả ML."""

TASK_DETECTION_USER = """
Mô tả bài toán: {user_query}
Thông tin dataset: {dataset_info}
Insight từ EDA: {eda_insights}

Xác định:
1. Loại bài toán: regression / classification / clustering
2. Cột target (nếu có)
3. Model nên thử: chọn 2-3 model từ danh sách bên dưới
4. Metric đánh giá phù hợp

Model có sẵn (CHỈ chọn từ danh sách này):
- regression: LinearRegression, Ridge, RandomForestRegressor, XGBRegressor
- classification: LogisticRegression, RandomForestClassifier, XGBClassifier
- clustering: KMeans

Trả về JSON:
{{
  "task_type": "regression|classification|clustering",
  "target_col": "tên cột hoặc null",
  "suggested_models": ["model1", "model2"],
  "metric": "rmse|f1|silhouette",
  "reason": "Lý do ngắn gọn"
}}
"""

ML_EXPLANATION_USER = """
Yêu cầu của người dùng: {user_query}

Kết quả model:
{model_results}

Feature importance:
{feature_importance}

Domain: {domain_context}

Giải thích kết quả bằng tiếng Việt, điều chỉnh mức độ kỹ thuật theo yêu cầu user:
1. Model nào tốt nhất và tại sao (kèm số liệu metric cụ thể)
2. Feature nào quan trọng nhất theo nghĩa thực tế
3. Model có thể tin cậy không (nhìn vào metric)
4. Gợi ý cải thiện cụ thể

Lưu ý: Nếu model_results rỗng hoặc null, bỏ qua hoàn toàn section 1-3, chỉ viết gợi ý chung.
"""
