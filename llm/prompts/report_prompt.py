"""Prompt cho report generator — tổng hợp EDA + ML thành báo cáo tiếng Việt."""

REPORT_SYSTEM = """
Bạn là chuyên gia viết báo cáo phân tích dữ liệu. Viết báo cáo rõ ràng,
chuyên nghiệp bằng tiếng Việt, phù hợp với người đọc không chuyên về kỹ thuật.
"""

REPORT_USER = """
Thông tin dataset: {dataset_info}
Kết quả EDA: {eda_results}
Kết quả ML (nếu có): {ml_results}
Nhật ký thực thi: {execution_log}

Viết báo cáo theo cấu trúc:

# Báo cáo phân tích dữ liệu

## 1. Tổng quan dataset
(Số file, số dòng, số cột, khoảng thời gian nếu là time series)

## 2. Chất lượng dữ liệu
(Missing value, outlier, duplicate phát hiện được và cách xử lý)

## 3. Insight chính
(3-5 insight quan trọng nhất từ EDA)

## 4. Kết quả mô hình (nếu có)
(Model tốt nhất, metric, so sánh các model)

## 5. Gợi ý cải thiện
(3 gợi ý cụ thể để phân tích hoặc cải thiện model tiếp theo)

## 6. Hạn chế
(Giới hạn của phân tích này)
"""
