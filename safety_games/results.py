"""Round observations, independent of reward and evaluation policy."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any

from .config import ExperimentMode, require_number, require_text


class RoundStatus(str, Enum):
    COMPLETED = "completed"
    LLM_ERROR = "llm_error"
    EXECUTION_ERROR = "execution_error"
    EVALUATION_ERROR = "evaluation_error"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


@dataclass(frozen=True)
class RoundResult:
    run_id: str
    round_index: int
    task_id: str
    mode: ExperimentMode
    model: str
    status: RoundStatus
    public_score: float | None = None
    protected_score: float | None = None
    reward: float | None = None
    duration_s: float | None = None
    execution_exit_code: int | None = None
    sandbox_image_id: str | None = None
    error_type: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("run_id", "task_id", "model"):
            require_text(name, getattr(self, name))
        require_number("round_index", self.round_index, minimum=1, integer=True)
        object.__setattr__(self, "mode", ExperimentMode(self.mode))
        object.__setattr__(self, "status", RoundStatus(self.status))
        for name in ("public_score", "protected_score", "reward"):
            value = getattr(self, name)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError(f"{name} must be a finite number or None")
        if self.duration_s is not None:
            require_number("duration_s", self.duration_s, minimum=0)
        if self.execution_exit_code is not None and type(self.execution_exit_code) is not int:
            raise ValueError("execution_exit_code must be an integer or None")
        for name in ("sandbox_image_id", "error_type"):
            if getattr(self, name) is not None:
                require_text(name, getattr(self, name))
        if not isinstance(self.timestamp, datetime) or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be a timezone-aware datetime")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mode"] = self.mode.value
        result["status"] = self.status.value
        result["timestamp"] = self.timestamp.astimezone(timezone.utc).isoformat()
        return {"schema_version": 1, **result}
