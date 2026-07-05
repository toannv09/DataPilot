"""Evaluation Agent — load model, predict trên test data, tính metrics, vẽ biểu đồ, nhận xét."""

import json

from sklearn.base import ClusterMixin, is_regressor
from sklearn.metrics import silhouette_score

from agents.base_agent import AgentResult, BaseAgent
from llm.client import MODEL_DEFAULT, call_llm
from llm.prompts.ml_prompt import ML_EXPLANATION_USER
from tools.ml.ml_viz import plot_actual_vs_predicted, plot_cluster_scatter, plot_confusion_matrix, plot_residuals
from tools.ml.metrics import compute_supervised_metrics
from tools.ml.preprocessor import handle_missing
from tools.ml.trainer import load_model_bundle


def _detect_task_type(model):
    if isinstance(model, ClusterMixin):
        return "clustering"
    if is_regressor(model):
        return "regression"
    return "classification"


class EvaluationAgent(BaseAgent):
    async def run(self, context=None):
        context = context or self.context
        self._status = "running"

        try:
            model_path = context.extra["model_path"]
            bundle = load_model_bundle(model_path)
            model = bundle["model"]
            pipeline = bundle.get("pipeline")
            task_type = bundle.get("task_type") or _detect_task_type(model)
            # Ưu tiên target_col đã lưu trong model — dropdown ở UI chỉ liệt kê cột có trong
            # file test mới upload, có thể không khớp tên hoặc bị bỏ sót.
            target_col = context.extra.get("target_col") or bundle.get("target_col")

            df = next(iter(context.files.values())).copy()

            if pipeline is not None:
                feature_df = df.drop(columns=[target_col]) if target_col and target_col in df.columns else df
                X = pipeline.transform(feature_df)
                y_true = df[target_col] if target_col and target_col in df.columns else None
            else:
                df_numeric = df.select_dtypes(include="number").copy()
                for col in df_numeric.columns:
                    if df_numeric[col].isna().any():
                        df_numeric = handle_missing(df_numeric, col, "median")

                y_true = df_numeric[target_col] if target_col and target_col in df_numeric.columns else None
                X = df_numeric.drop(columns=[target_col]) if target_col and target_col in df_numeric.columns else df_numeric

            feature_names = bundle.get("feature_names")
            if feature_names:
                X = X[[c for c in feature_names if c in X.columns]]

            # Loại dòng thiếu target — không có nhãn thật thì không đánh giá được, dù feature đã được
            # pipeline.transform() điền thiếu, target lấy riêng từ df gốc nên có thể vẫn còn NaN.
            if y_true is not None and y_true.isna().any():
                valid_idx = y_true.dropna().index
                y_true = y_true.loc[valid_idx]
                X = X.loc[valid_idx]

            charts = []
            if task_type == "regression":
                y_pred = model.predict(X)
                metrics = compute_supervised_metrics("regression", y_true, y_pred)
                charts.append(plot_actual_vs_predicted(y_true, y_pred))
                charts.append(plot_residuals(y_true, y_pred))
            elif task_type == "classification":
                y_pred = model.predict(X)
                metrics = compute_supervised_metrics("classification", y_true, y_pred)
                charts.append(plot_confusion_matrix(y_true, y_pred))
            else:
                if hasattr(model, "predict"):
                    labels = model.predict(X)
                    metrics = {}
                    if len(set(labels)) > 1:
                        metrics["silhouette"] = float(silhouette_score(X, labels))
                    charts.append(plot_cluster_scatter(X, labels))
                else:
                    metrics = {"note": "Model clustering này (vd DBSCAN) không hỗ trợ predict trên dữ liệu mới."}

            comment = call_llm(
                ML_EXPLANATION_USER.format(
                    user_query=context.user_query or "(không có yêu cầu cụ thể)",
                    model_results=json.dumps(metrics, ensure_ascii=False),
                    feature_importance="{}",
                    domain_context=context.domain_context,
                ),
                model=MODEL_DEFAULT,
            )

            self._status = "done"
            return AgentResult(success=True, summary=comment, data={"metrics": metrics}, charts=charts)
        except Exception as e:
            self._status = "error"
            return AgentResult(success=False, error=str(e))

    async def get_status(self):
        return self._status
