"""Provider-neutral synchronous contract for API and local model adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from .config import LLMConfig, require_number


class LLMError(RuntimeError):
    """Adapter failures; messages must not contain credentials or raw requests."""


class LLMUnavailable(LLMError):
    """Model, local runtime or provider is unavailable."""


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("system", "user", "assistant"):
            raise ValueError("unsupported message role")
        if not isinstance(self.content, str):
            raise TypeError("message content must be a string")


@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[Message, ...]
    config: LLMConfig
    seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.messages, tuple) or not self.messages or not all(isinstance(m, Message) for m in self.messages):
            raise ValueError("messages must be a nonempty tuple of Message objects")
        if not isinstance(self.config, LLMConfig):
            raise TypeError("config must be LLMConfig")
        if self.seed is not None:
            require_number("generation seed", self.seed, minimum=0, integer=True)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not isinstance(self.model, str) or not self.model:
            raise ValueError("response requires string text and a nonempty model identifier")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None:
                require_number(name, value, minimum=0, integer=True)


class LLMClient(ABC):
    """Implement generate in an API/local adapter; no SDK is loaded here.

    Adapters own authentication and timeout enforcement. Unsupported settings
    (including seed) must raise LLMError instead of being silently ignored.
    No automatic retries: a retry may affect the experimental trajectory.
    """

    @abstractmethod
    def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate one response or raise LLMError."""
        raise NotImplementedError
