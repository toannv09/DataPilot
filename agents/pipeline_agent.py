"""Pipeline Agent — chạy theo stage: EDA -> Xử lý -> Huấn luyện -> Đánh giá -> Báo cáo tổng hợp.

Chạy theo stage (run_stage) để UI có thể dừng/confirm giữa các bước (human-in-the-loop).
context.extra["stop_after"]: "eda" | "preprocessing" | "training" | None (chạy hết) — dùng khi gọi run() trực tiếp.
"""

from dataclasses import replace

import joblib
import pandas as pd

from agents import report_generator
from agents.base_agent import AgentResult, BaseAgent
from agents.eda_agent import EDAAgent
from agents.evaluation_agent import EvaluationAgent
from agents.preprocessing_agent import PreprocessingAgent
from agents.training_agent import TrainingAgent

STAGES = ["eda", "preprocessing", "training", "evaluation"]


class PipelineAgent(BaseAgent):
    async def run_stage(self, stage, context, steps):
        """Chạy 1 stage, cập nhật context.extra/context.files tại chỗ, ghi kết quả vào steps."""
        context.extra.setdefault("original_files", list(context.files.keys()))

        if stage == "eda":
            result = await EDAAgent(context).run(context)
            if result.success:
                context.extra["eda_insights"] = result.insights

        elif stage == "preprocessing":
            if context.extra.get("raw_df") is not None:
                # Chạy lại stage này (sau góp ý) -> context.files hiện đang là data ĐÃ xử lý
                # từ lần trước, phải phục hồi data thô để không xử lý 2 lần (double scale/encode).
                context.files = {"raw": context.extra["raw_df"]}
            raw_df = next(iter(context.files.values()))
            result = await PreprocessingAgent(context).run(context)
            if result.success:
                context.extra["raw_df"] = raw_df
                processed_df = pd.read_csv(result.data["processed_path"])
                context.files = {"processed": processed_df}
                context.extra["preprocessing_pipeline"] = joblib.load(result.data["pipeline_path"])

        elif stage == "training":
            result = await TrainingAgent(context).run(context)
            if result.success:
                context.extra["model_path"] = result.data["model_path"]
                context.extra["target_col"] = result.data["target_col"]

        elif stage == "evaluation":
            # Evaluation cần dữ liệu thô (chưa qua pipeline) -> EvaluationAgent tự áp pipeline.transform.
            # Ưu tiên dùng file test riêng do người dùng upload, nếu không có thì dùng lại dữ liệu huấn luyện.
            eval_context = context
            if context.extra.get("test_df") is not None:
                eval_context = replace(context, files={"test": context.extra["test_df"]})
            elif "raw_df" in context.extra:
                eval_context = replace(context, files={"raw": context.extra["raw_df"]})
            result = await EvaluationAgent(eval_context).run(eval_context)

        else:
            raise ValueError(f"stage không hợp lệ: {stage}")

        steps[stage] = result
        return result

    async def run(self, context=None):
        context = context or self.context
        self._status = "running"
        steps = {}

        try:
            stop_after = context.extra.get("stop_after")

            for stage in STAGES:
                result = await self.run_stage(stage, context, steps)
                if not result.success or stop_after == stage:
                    break

            return self.finalize(context, steps)
        except Exception as e:
            self._status = "error"
            return AgentResult(success=False, error=str(e), data={"steps": steps})

    def finalize(self, context, steps):
        all_charts = []
        execution_log = []
        for name, result in steps.items():
            all_charts.extend(result.charts)
            execution_log.extend(result.log)
            execution_log.append({
                "step": name,
                "status": "success" if result.success else "error",
                "summary": result.summary,
                "error": result.error,
            })

        eda_results = steps["eda"].data.get("results", {}) if "eda" in steps else {}
        ml_results = steps["training"].data if "training" in steps else None
        if "evaluation" in steps:
            ml_results = {**(ml_results or {}), "evaluation_metrics": steps["evaluation"].data.get("metrics")}

        dataset_info = {
            "files": context.extra.get("original_files", list(context.files.keys())),
            "problem_name": context.problem_name,
            "experiment_type": context.experiment_type,
        }

        report_path = report_generator.generate(
            dataset_info=dataset_info,
            eda_results=eda_results,
            ml_results=ml_results,
            execution_log=execution_log,
            charts=all_charts,
        )

        self._status = "done"
        return AgentResult(
            success=True,
            summary="Pipeline hoàn tất.",
            data={"steps": steps, "report_path": report_path},
            charts=all_charts,
            log=execution_log,
        )

    async def get_status(self):
        return self._status
