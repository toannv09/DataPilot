"""Nhận experiment_type → trả về agent tương ứng."""

from agents.eda_agent import EDAAgent
from agents.evaluation_agent import EvaluationAgent
from agents.inference_agent import InferenceAgent
from agents.pipeline_agent import PipelineAgent
from agents.preprocessing_agent import PreprocessingAgent
from agents.training_agent import TrainingAgent


def route(experiment_type, context):
    agents = {
        "Khám phá dữ liệu": EDAAgent(context),
        "Xử lý dữ liệu": PreprocessingAgent(context),
        "Huấn luyện mô hình": TrainingAgent(context),
        "Đánh giá mô hình": EvaluationAgent(context),
        "Suy luận mô hình": InferenceAgent(context),
        "Tùy chỉnh": None,
        "Full Pipeline": PipelineAgent(context),
    }
    return agents.get(experiment_type)
