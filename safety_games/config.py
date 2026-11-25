"""Validated, immutable configuration without provider SDK dependencies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from enum import Enum
import math
from pathlib import Path
import re
import tomllib
from typing import Any


class ConfigError(ValueError):
    """Invalid or unsupported experiment configuration."""


class ExperimentMode(str, Enum):
    BASELINE = "baseline"
    FIXED_PENALTY = "fixed_penalty"
    ESCALATING_PENALTY = "escalating_penalty"
    REPUTATION = "reputation"


def require_text(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a nonempty string")


def require_number(
    name: str, value: Any, *, minimum: float, maximum: float | None = None,
    integer: bool = False,
) -> None:
    valid_type = type(value) is int if integer else type(value) in (int, float)
    if not valid_type or not math.isfinite(value) or value < minimum:
        raise ConfigError(f"{name} must be a finite {'integer' if integer else 'number'} >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be <= {maximum}")


@dataclass(frozen=True)
class LLMConfig:
    backend: str = "api"
    model: str = "unconfigured"
    temperature: float = 0.0
    max_output_tokens: int = 1024
    timeout_s: float = 60.0
    api_key_env: str | None = None
    base_url: str = "https://api.groq.com/openai/v1"
    reasoning_effort: str = "medium"
    max_retries: int = 3
    groq_channel_workaround: bool = False

    def __post_init__(self) -> None:
        if self.backend not in ("api", "local"):
            raise ConfigError("llm.backend must be 'api' or 'local'")
        require_text("llm.model", self.model)
        require_number("llm.temperature", self.temperature, minimum=0, maximum=2)
        require_number("llm.max_output_tokens", self.max_output_tokens, minimum=1, integer=True)
        require_number("llm.timeout_s", self.timeout_s, minimum=0.001)
        require_text("llm.base_url", self.base_url)
        if self.reasoning_effort not in ("low", "medium", "high"):
            raise ConfigError("llm.reasoning_effort must be low, medium or high")
        require_number("llm.max_retries", self.max_retries, minimum=0, maximum=5, integer=True)
        if type(self.groq_channel_workaround) is not bool:
            raise ConfigError('llm.groq_channel_workaround must be boolean')
        if self.api_key_env is not None:
            if not isinstance(self.api_key_env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.api_key_env):
                raise ConfigError("llm.api_key_env must be an environment variable name")


@dataclass(frozen=True)
class SandboxConfig:
    image: str = "safety-games-sandbox:local"
    timeout_s: float = 5.0
    memory_mb: int = 128
    cpus: float = 0.5
    pids_limit: int = 32
    tmpfs_mb: int = 16
    max_output_bytes: int = 65536
    max_source_bytes: int = 262144
    max_stdin_bytes: int = 262144

    def __post_init__(self) -> None:
        if not isinstance(self.image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:-]*", self.image):
            raise ConfigError("sandbox.image must be a Docker image reference")
        require_number("sandbox.timeout_s", self.timeout_s, minimum=0.001)
        require_number("sandbox.cpus", self.cpus, minimum=0.01)
        for name in ("memory_mb", "pids_limit", "tmpfs_mb", "max_output_bytes", "max_source_bytes", "max_stdin_bytes"):
            require_number(f"sandbox.{name}", getattr(self, name), minimum=1, integer=True)
        if self.memory_mb < 32:
            raise ConfigError("sandbox.memory_mb must be >= 32 for Python startup")
        if self.tmpfs_mb > self.memory_mb:
            raise ConfigError("sandbox.tmpfs_mb must not exceed memory_mb")


@dataclass(frozen=True)
class AgentConfig:
    max_tool_calls: int = 15
    max_steps: int = 20
    episode_timeout_s: float = 900.0
    max_episode_tokens: int = 24000
    max_input_estimate: int = 5500
    tool_feedback_chars: int = 3000
    command_timeout_s: float = 15.0
    max_workspace_bytes: int = 1048576
    max_workspace_files: int = 64
    max_tool_parse_errors: int = 2

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            require_number(f"agent.{item.name}", value, minimum=1, integer=type(item.default) is int)


@dataclass(frozen=True)
class APIBudgetConfig:
    requests_per_minute: int = 30
    requests_per_day: int = 1000
    tokens_per_minute: int = 8000
    tokens_per_day: int = 200000
    experiment_token_limit: int = 180000

    def __post_init__(self) -> None:
        for item in fields(self):
            require_number(f"budget.{item.name}", getattr(self, item.name), minimum=1, integer=True)
        if self.experiment_token_limit > self.tokens_per_day:
            raise ConfigError("experiment_token_limit must not exceed daily token limit")


@dataclass(frozen=True)
class ExperimentConfig:
    name: str = "baseline"
    mode: ExperimentMode = ExperimentMode.BASELINE
    rounds: int = 1
    seed: int = 0
    output_dir: Path = Path("runs")
    llm: LLMConfig = field(default_factory=LLMConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    budget: APIBudgetConfig = field(default_factory=APIBudgetConfig)
    task_manifest: Path = Path("data/manifest.json")
    prompt_path: Path = Path("prompts/coding_agent_v1.txt")

    def __post_init__(self) -> None:
        require_text("name", self.name)
        try:
            object.__setattr__(self, "mode", ExperimentMode(self.mode))
        except (ValueError, TypeError) as exc:
            raise ConfigError("unknown experiment mode") from exc
        require_number("rounds", self.rounds, minimum=1, integer=True)
        require_number("seed", self.seed, minimum=0, integer=True)
        if not isinstance(self.output_dir, (str, Path)) or not str(self.output_dir).strip():
            raise ConfigError("output_dir must be a nonempty path")
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        if not isinstance(self.llm, LLMConfig) or not isinstance(self.sandbox, SandboxConfig):
            raise ConfigError("llm and sandbox must be validated configuration objects")
        if not isinstance(self.agent, AgentConfig) or not isinstance(self.budget, APIBudgetConfig):
            raise ConfigError("agent and budget must be validated configuration objects")
        for name in ("task_manifest", "prompt_path"):
            value = getattr(self, name)
            if not isinstance(value, (str, Path)) or not str(value).strip():
                raise ConfigError(f"{name} must be a path")
            object.__setattr__(self, name, Path(value))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mode"] = self.mode.value
        result["output_dir"] = str(self.output_dir)
        result["task_manifest"] = str(self.task_manifest)
        result["prompt_path"] = str(self.prompt_path)
        return result


def _construct(cls: type, data: Any) -> Any:
    if not isinstance(data, dict):
        raise ConfigError(f"{cls.__name__} must be a TOML table")
    unknown = set(data) - {item.name for item in fields(cls)}
    if unknown:
        raise ConfigError(f"unknown {cls.__name__} keys: {', '.join(sorted(unknown))}")
    return cls(**data)


def load_config(path: str | Path) -> ExperimentConfig:
    """Load TOML; output_dir is relative to the caller's current directory."""
    try:
        with Path(path).open("rb") as stream:
            data = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML: {exc}") from exc
    data["llm"] = _construct(LLMConfig, data.get("llm", {}))
    data["sandbox"] = _construct(SandboxConfig, data.get("sandbox", {}))
    data["agent"] = _construct(AgentConfig, data.get("agent", {}))
    data["budget"] = _construct(APIBudgetConfig, data.get("budget", {}))
    return _construct(ExperimentConfig, data)
