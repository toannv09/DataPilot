"""Abstract class và data structures dùng chung cho tất cả agent."""

from dataclasses import dataclass, field


@dataclass
class ExperimentContext:
    """Thông tin bài toán + experiment hiện tại, truyền vào mọi agent."""

    problem_name: str = ""
    problem_description: str = ""
    experiment_type: str = ""
    files: dict = field(default_factory=dict)        # filename -> DataFrame
    file_paths: dict = field(default_factory=dict)   # filename -> path trên disk
    domain_context: str = ""
    user_query: str = ""
    extra: dict = field(default_factory=dict)        # output từ agent trước (dùng trong pipeline)


@dataclass
class AgentResult:
    """Kết quả trả về sau khi agent chạy xong."""

    success: bool
    summary: str = ""
    data: dict = field(default_factory=dict)
    charts: list = field(default_factory=list)
    insights: str = ""
    log: list = field(default_factory=list)
    error: str = None


class BaseAgent:
    """Interface chung cho tất cả agent."""

    def __init__(self, context: ExperimentContext):
        self.context = context
        self._status = "idle"

    async def run(self, context: ExperimentContext = None) -> AgentResult:
        raise NotImplementedError

    async def get_status(self) -> str:
        return self._status
