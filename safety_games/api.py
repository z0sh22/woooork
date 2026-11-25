"""Small OpenAI-compatible client with durable quotas and bounded transport retries."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from .artifacts import SecretRedactor, exclusive_run, write_json
from .config import APIBudgetConfig, LLMConfig
from .llm import GenerationRequest, LLMClient, LLMError, LLMResponse, LLMUnavailable


class BudgetExceeded(LLMError):
    pass


@dataclass(frozen=True)
class ChatTurn:
    message: dict
    usage: dict
    model: str
    request_id: str | None
    finish_reason: str | None
    charged_tokens: int | None = None
    tool_parse_error: dict | None = None


class ToolCallingClient(LLMClient, ABC):
    @abstractmethod
    def complete(self, messages: list[dict], tools: list[dict], *, deadline: float | None = None, token_budget: int | None = None) -> ChatTurn:
        raise NotImplementedError

    @staticmethod
    def estimate_tokens(messages: list[dict], tools: list[dict]) -> int:
        serialized = json.dumps({'messages':messages,'tools':tools},ensure_ascii=False)
        return max(1,(len(serialized.encode('utf-8'))+2)//3+128)

    def generate(self, request: GenerationRequest) -> LLMResponse:
        if request.seed is not None:
            raise LLMError("This adapter does not send an unverified provider seed")
        if request.config != self.config:
            raise LLMError("Request configuration differs from client configuration")
        turn = self.complete([{"role": m.role, "content": m.content} for m in request.messages], [])
        return LLMResponse(turn.message.get("content") or "", turn.model,
                           turn.usage.get("prompt_tokens"), turn.usage.get("completion_tokens"), turn.request_id)


def load_api_key(name: str = "GROQ_API_KEY") -> str:
    if not os.environ.get(name):
        try:
            from dotenv import load_dotenv
        except ImportError as exc:
            raise LLMUnavailable("Install requirements.txt, or set GROQ_API_KEY in the process environment") from exc
        load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
    key = os.environ.get(name, "").strip()
    if not key:
        raise LLMUnavailable(f"Required environment variable {name} is not configured")
    return key


class QuotaLedger:
    """One account ledger, including attempted requests across experiments/resumes.

    Unknown usage remains reserved rather than silently refunded. UTC dates are
    a conservative local daily guard; provider headers/429 remain authoritative.
    """
    def __init__(self, path: Path, config: APIBudgetConfig, *, clock=time.time, sleep=time.sleep):
        self.path, self.config, self.clock, self.sleep = path, config, clock, sleep
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"schema_version": 1, "requests": []}

    def reserve(self, tokens: int, *, deadline: float | None = None) -> str:
        if tokens > self.config.tokens_per_minute:
            raise BudgetExceeded("Request estimate exceeds tokens_per_minute")
        while True:
            now = self.clock()
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            with exclusive_run(self.path.with_suffix(".lock")):
                ledger = self._load()
                recent = [r for r in ledger["requests"] if now - r["time"] < 60]
                daily = [r for r in ledger["requests"] if r["day"] == day]
                if len(daily) >= self.config.requests_per_day or sum(r["tokens"] for r in daily) + tokens > self.config.tokens_per_day:
                    raise BudgetExceeded("Local daily API quota exhausted; resume after reset")
                if len(recent) < self.config.requests_per_minute and sum(r["tokens"] for r in recent) + tokens <= self.config.tokens_per_minute:
                    import uuid
                    identifier = uuid.uuid4().hex
                    ledger["requests"].append({"id": identifier, "time": now, "day": day, "tokens": tokens, "usage_known": False})
                    write_json(self.path, ledger)
                    return identifier
                delay = max(0.1, min(r["time"] + 60.1 - now for r in recent))
            if deadline is not None and time.monotonic() + delay >= deadline:
                raise BudgetExceeded("Episode deadline would expire while waiting for API quota")
            self.sleep(delay)

    def settle(self, identifier: str, actual_tokens: int) -> None:
        with exclusive_run(self.path.with_suffix(".lock")):
            ledger = self._load()
            for record in ledger["requests"]:
                if record["id"] == identifier:
                    record.update(tokens=actual_tokens, usage_known=True)
                    break
            else:
                raise LLMError("Quota reservation not found")
            write_json(self.path, ledger)


def retry_delay(value: str | None, attempt: int, *, now: float | None = None) -> float:
    delay = min(60.0, 2.0 ** attempt)
    if value:
        try:
            supplied = float(value)
        except ValueError:
            try:
                supplied = parsedate_to_datetime(value).timestamp() - (time.time() if now is None else now)
            except (ValueError, TypeError, OverflowError):
                supplied = 0
        delay = max(delay, supplied)
    if not 0 <= delay <= 120:
        raise BudgetExceeded("Retry-After exceeds the bounded retry wait; resume later")
    return delay


class OpenAICompatibleClient(ToolCallingClient):
    def __init__(self, config: LLMConfig, ledger: QuotaLedger, *, key: str | None = None, opener=None, sleep=time.sleep, event=None):
        self.config, self.ledger = config, ledger
        self._key = key if key is not None else load_api_key(config.api_key_env or "GROQ_API_KEY")
        self.redactor = SecretRedactor((self._key,))
        self.opener = opener or urllib.request.build_opener()
        self.sleep, self.event = sleep, event

    @staticmethod
    def estimate_tokens(messages: list[dict], tools: list[dict]) -> int:
        # Approximation, not a tokenizer; leave margin and honor server 429.
        serialized = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False)
        return max(1, (len(serialized.encode("utf-8")) + 2) // 3 + 128)

    def _emit(self, event: dict):
        if self.event:
            self.event(self.redactor.clean(event))

    def check_model(self) -> dict:
        request = urllib.request.Request(self.config.base_url.rstrip("/") + "/models",
                                         headers={"Authorization": "Bearer " + self._key, "User-Agent": "safety-games/1.0"})
        try:
            with self.opener.open(request, timeout=self.config.timeout_s) as response:
                data = json.loads(response.read(2 * 1024 * 1024))
        except (urllib.error.URLError, ValueError, OSError) as exc:
            raise LLMUnavailable("Model availability check failed (credentials/network/provider)") from None
        model = next((m for m in data.get("data", []) if m.get("id") == self.config.model), None)
        if model is None or model.get("active") is False:
            raise LLMUnavailable("Configured model is not available on this account")
        return {"model": model["id"], "available": True, "inference_performed": False}

    def complete(self, messages, tools, *, deadline=None, token_budget=None):
        payload = {"model": self.config.model, "messages": messages,
                   "temperature": self.config.temperature, "max_completion_tokens": self.config.max_output_tokens,
                   "stream": False}
        if tools:
            if any(tool.get("type") != "function" for tool in tools):
                raise LLMError("Only controller-owned function tools are supported")
            payload.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
            if self.config.groq_channel_workaround:
                if self.config.base_url.rstrip('/')!='https://api.groq.com/openai/v1':
                    raise LLMError('Groq compatibility flag cannot be sent to another provider')
                # Execution still requires our local tool allowlist and schema.
                payload['disable_tool_validation']=True
        if self.config.model.startswith("openai/gpt-oss"):
            payload.update(reasoning_effort=self.config.reasoning_effort, include_reasoning=True)
        estimate = self.estimate_tokens(messages, tools) + self.config.max_output_tokens
        charged = 0
        for attempt in range(self.config.max_retries + 1):
            if deadline is not None and time.monotonic() >= deadline:
                raise BudgetExceeded("Episode deadline exhausted")
            if token_budget is not None and charged + estimate > token_budget:
                raise BudgetExceeded('Retry/request would exceed the remaining episode/experiment token budget')
            identifier = self.ledger.reserve(estimate, deadline=deadline)
            charged += estimate
            self._emit({"type": "api_attempt", "attempt": attempt + 1, "reservation_id": identifier, "reserved_tokens": estimate,
                        "request_payload":payload})
            request = urllib.request.Request(
                self.config.base_url.rstrip("/") + "/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": "Bearer " + self._key, "Content-Type": "application/json", "User-Agent": "safety-games/1.0"},
            )
            try:
                timeout = self.config.timeout_s if deadline is None else min(self.config.timeout_s, max(0.1, deadline - time.monotonic()))
                with self.opener.open(request, timeout=timeout) as response:
                    raw = response.read(4 * 1024 * 1024 + 1)
                    headers=getattr(response,'headers',{})
                    rate_headers={name:headers.get(name) for name in ('x-ratelimit-limit-requests','x-ratelimit-limit-tokens',
                                  'x-ratelimit-remaining-requests','x-ratelimit-remaining-tokens','x-ratelimit-reset-requests','x-ratelimit-reset-tokens')
                                  if headers.get(name) is not None}
                    if len(raw) > 4 * 1024 * 1024:
                        raise LLMError("API response exceeded the byte limit")
                    result = json.loads(raw)
                usage = result.get("usage") or {}
                actual = usage.get("total_tokens")
                if type(actual) is int and actual >= 0:
                    self.ledger.settle(identifier, actual)
                    charged += actual - estimate
                else:
                    raise LLMError("Provider omitted token usage; reservation retained")
                choice = result["choices"][0]
                message = choice["message"]
                if message.get("role") != "assistant":
                    raise LLMError("Provider returned an invalid assistant message")
                self._emit({"type": "api_usage", "reservation_id": identifier, "usage": usage, "model": result.get("model"),
                            'response':result,'rate_limit_headers':rate_headers})
                return ChatTurn(message, usage, result.get("model", self.config.model), result.get("id"), choice.get("finish_reason"), charged)
            except urllib.error.HTTPError as exc:
                status, retry_after = exc.code, exc.headers.get("Retry-After")
                try:
                    raw_error=exc.read(65536)
                    error_payload=json.loads(raw_error)
                    error_details={k:error_payload.get('error',{}).get(k) for k in ('message','type','code','failed_generation')}
                except (ValueError, TypeError, OSError, AttributeError):
                    error_details={'parseable_error':False}
                exc.close()
                self._emit({"type": "api_error", "http_status": status, "attempt": attempt + 1,'details':error_details})
                if status==400 and error_details.get('code')=='tool_use_failed':
                    # Do not invent a parsed call, usage, or an assistant message.
                    # The agent loop logs the raw provider failure and returns
                    # neutral format feedback within a bounded episode.
                    return ChatTurn({}, {}, self.config.model, None, 'tool_parse_error', charged, error_details)
                if status not in (429, 408, 500, 502, 503, 504) or attempt == self.config.max_retries:
                    raise LLMError(f"API HTTP {status}; sanitized details saved in the external event log") from None
                delay = retry_delay(retry_after, attempt + 1)
            except (urllib.error.URLError, TimeoutError, OSError):
                self._emit({"type": "api_error", "error_type": "transport", "attempt": attempt + 1})
                if attempt == self.config.max_retries:
                    raise LLMUnavailable("API transport retries exhausted") from None
                delay = retry_delay(None, attempt + 1)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMError("Malformed API response; reservation retained") from None
            if deadline is not None and time.monotonic() + delay >= deadline:
                raise BudgetExceeded("Retry would exceed episode deadline")
            self._emit({"type": "api_retry_wait", "seconds": delay})
            self.sleep(delay)
        raise LLMError("Retry loop exhausted")
