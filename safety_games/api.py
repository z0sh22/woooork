"""Small OpenAI-compatible client with durable quotas and bounded transport retries."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from .artifacts import SecretRedactor, exclusive_run, write_json
from .config import APIBudgetConfig, LLMConfig
from .llm import GenerationRequest, LLMClient, LLMError, LLMResponse, LLMUnavailable


class BudgetExceeded(LLMError):
    def __init__(self, message, *, kind='episode_token_limit', charged_tokens=0):
        super().__init__(message)
        self.kind, self.charged_tokens = kind, charged_tokens


class APIRequestError(LLMError):
    def __init__(self, message, *, charged_tokens=0, reason='api_error'):
        super().__init__(message)
        self.charged_tokens = charged_tokens
        self.reason = reason


def token_breakdown(usage):
    """Reasoning is a subset of completion, never an additional token charge."""
    details = usage.get('completion_tokens_details') or {}
    reasoning = details.get('reasoning_tokens') if isinstance(details, dict) else None
    output = usage.get('completion_tokens')
    if type(reasoning) is not int or reasoning < 0 or type(output) is not int or reasoning > output:
        reasoning = None
    return {'input_tokens': usage.get('prompt_tokens'), 'output_tokens': output,
            'reasoning_tokens': reasoning,
            'non_reasoning_output_tokens': output - reasoning if reasoning is not None else None}


def output_allowance(config, budget, input_estimate, remaining=None):
    """Plan one request, including input, output and an explicit TPM margin."""
    if not config.adaptive_output_budget:
        return config.max_output_tokens
    available = budget.tokens_per_minute - config.request_token_margin - input_estimate
    if remaining is not None:
        available = min(available, remaining - input_estimate)
    output = min(config.max_output_tokens, available)
    if output < config.min_output_tokens:
        kind = 'context_limit' if input_estimate + config.min_output_tokens + config.request_token_margin > budget.tokens_per_minute else 'episode_token_limit'
        raise BudgetExceeded('Insufficient request/episode budget for minimum output', kind=kind)
    return output


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
    def complete(self, messages: list[dict], tools: list[dict], *, deadline: float | None = None, token_budget: int | None = None, max_output_tokens: int | None = None) -> ChatTurn:
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

    Unknown usage remains reserved. A rolling 24-hour guard avoids assuming a
    provider reset at UTC midnight; provider headers can only tighten it.
    """
    def __init__(self, path: Path, config: APIBudgetConfig, *, clock=time.time, sleep=time.sleep):
        self.path, self.config, self.clock, self.sleep = path, config, clock, sleep
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"schema_version": 1, "requests": []}

    def daily_status(self, required_tokens=0):
        """Read-only scheduling estimate; never clears usage after key rotation."""
        now = self.clock()
        with exclusive_run(self.path.with_suffix('.lock')):
            records = sorted((r for r in self._load()['requests'] if now-r['time'] < 86400), key=lambda r:r['time'])
        used = sum(r['tokens'] for r in records)
        ceiling = self.config.tokens_per_day-self.config.daily_token_headroom
        remaining, count, ready = ceiling-used, len(records), now
        if required_tokens > ceiling:
            ready = None
        elif remaining < required_tokens or count >= self.config.requests_per_day:
            for record in records:
                remaining += record['tokens']; count -= 1
                if remaining >= required_tokens and count < self.config.requests_per_day:
                    ready = record['time']+86400+.1
                    break
        return {'rolling24h_charged_tokens':used, 'rolling24h_attempts':len(records),
                'available_tokens':ceiling-used, 'required_tokens':required_tokens,
                'ready_at_epoch':ready, 'ready_now':ready is not None and ready <= now}

    def require_daily_capacity(self, tokens):
        with exclusive_run(self.path.with_suffix('.lock')):
            records = [r for r in self._load()['requests'] if self.clock() - r['time'] < 86400]
            available = self.config.tokens_per_day - self.config.daily_token_headroom - sum(r['tokens'] for r in records)
            if available < tokens or len(records) >= self.config.requests_per_day:
                raise BudgetExceeded('Insufficient rolling daily headroom for a new episode; resume later', kind='daily_quota')

    def reserve(self, tokens: int, *, deadline: float | None = None) -> str:
        if tokens > self.config.tokens_per_minute:
            raise BudgetExceeded("Request estimate exceeds tokens_per_minute", kind='context_limit')
        while True:
            now = self.clock()
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            with exclusive_run(self.path.with_suffix(".lock")):
                ledger = self._load()
                recent = [r for r in ledger["requests"] if now - r["time"] < 60]
                daily = [r for r in ledger["requests"] if now - r['time'] < 86400]
                if len(daily) >= self.config.requests_per_day or sum(r["tokens"] for r in daily) + tokens > self.config.tokens_per_day - self.config.daily_token_headroom:
                    raise BudgetExceeded("Local rolling daily API quota exhausted; resume after reset", kind='daily_quota')
                provider = ledger.get('provider_limits', {})
                blocked = [v['until'] - now for key, v in provider.items()
                           if v['until'] > now and v['remaining'] < (tokens if key == 'tokens' else 1)]
                if not blocked and len(recent) < self.config.requests_per_minute and sum(r["tokens"] for r in recent) + tokens <= self.config.tokens_per_minute:
                    import uuid
                    identifier = uuid.uuid4().hex
                    ledger["requests"].append({"id": identifier, "time": now, "day": day, "tokens": tokens, "usage_known": False})
                    write_json(self.path, ledger)
                    return identifier
                delay = max(0.1, min(blocked) if blocked else min(r["time"] + 60.1 - now for r in recent))
            if deadline is not None and time.monotonic() + delay >= deadline:
                raise BudgetExceeded("Episode deadline would expire while waiting for API quota", kind='time_limit')
            self.sleep(min(delay, 30.0))

    def observe_headers(self, headers):
        normalized = {str(k).lower(): str(v) for k, v in headers.items()}
        now = self.clock()
        updates = {}
        for key in ('tokens', 'requests'):
            remaining = normalized.get('x-ratelimit-remaining-' + key)
            reset = normalized.get('x-ratelimit-reset-' + key, '')
            parts = re.findall(r'(\d+(?:\.\d+)?)(ms|h|m|s)', reset)
            if remaining is not None and parts and ''.join(n + u for n, u in parts) == reset:
                try:
                    seconds = sum(float(n) * {'ms': .001, 'h': 3600, 'm': 60, 's': 1}[u] for n, u in parts)
                    updates[key] = {'remaining': max(0, int(remaining)), 'until': now + seconds}
                except (ValueError, OverflowError):
                    continue
        if updates:
            with exclusive_run(self.path.with_suffix('.lock')):
                ledger = self._load()
                ledger.setdefault('provider_limits', {}).update(updates)
                write_json(self.path, ledger)

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
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            self._emit({'type':'model_check_error','http_status':status})
            raise LLMUnavailable(f'Model availability check failed: HTTP {status}') from None
        except (urllib.error.URLError, ValueError, OSError) as exc:
            self._emit({'type':'model_check_error','error_type':type(exc).__name__})
            raise LLMUnavailable('Model availability check failed: ' + type(exc).__name__) from None
        model = next((m for m in data.get("data", []) if m.get("id") == self.config.model), None)
        if model is None or model.get("active") is False:
            raise LLMUnavailable("Configured model is not available on this account")
        return {"model": model["id"], "available": True, "inference_performed": False}

    def complete(self, messages, tools, *, deadline=None, token_budget=None, max_output_tokens=None):
        input_estimate = self.estimate_tokens(messages, tools)
        output = output_allowance(self.config, self.ledger.config, input_estimate, token_budget)
        if max_output_tokens is not None:
            if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= output:
                raise LLMError('Invalid per-request output allowance')
            output = max_output_tokens
        payload = {"model": self.config.model, "messages": messages,
                   "temperature": self.config.temperature, "max_completion_tokens": output,
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
        estimate = input_estimate + output
        charged = 0
        for attempt in range(self.config.max_retries + 1):
            if deadline is not None and time.monotonic() >= deadline:
                raise BudgetExceeded("Episode deadline exhausted", kind='time_limit', charged_tokens=charged)
            if token_budget is not None and charged + estimate > token_budget:
                raise BudgetExceeded('Retry/request would exceed the remaining episode/experiment token budget', charged_tokens=charged)
            try:
                identifier = self.ledger.reserve(estimate, deadline=deadline)
            except BudgetExceeded as exc:
                exc.charged_tokens += charged
                raise
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
                    self.ledger.observe_headers(rate_headers)
                    if len(raw) > 4 * 1024 * 1024:
                        raise LLMError("API response exceeded the byte limit")
                    result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError('API response must be an object')
                usage = result.get("usage") or {}
                if not isinstance(usage, dict):
                    raise ValueError('API usage must be an object')
                actual = usage.get("total_tokens")
                if type(actual) is int and actual >= 0:
                    self.ledger.settle(identifier, actual)
                    charged += actual - estimate
                else:
                    self._emit({'type':'api_malformed_response','reason':'missing_usage','response':result})
                    raise APIRequestError("Provider omitted token usage; reservation retained", charged_tokens=charged, reason='missing_usage')
                self._emit({"type": "api_usage", "reservation_id": identifier, "usage": usage, "model": result.get("model"),
                            'response':result,'rate_limit_headers':rate_headers,'token_breakdown':token_breakdown(usage),
                            'input_token_estimate': input_estimate, 'output_allowance': output})
                choices = result.get('choices')
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                    raise ValueError('Expected exactly one choice')
                choice = choices[0]
                message = choice.get('message')
                if not isinstance(message, dict) or message.get('role') != 'assistant':
                    raise ValueError('Invalid assistant message')
                return ChatTurn(message, usage, result.get("model", self.config.model), result.get("id"), choice.get("finish_reason"), charged)
            except urllib.error.HTTPError as exc:
                status, retry_after = exc.code, exc.headers.get("Retry-After")
                self.ledger.observe_headers(dict(exc.headers))
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
                    raise APIRequestError(f"API HTTP {status}; sanitized details saved in the external event log", charged_tokens=charged, reason='http_' + str(status)) from None
                try:
                    delay = retry_delay(retry_after, attempt + 1)
                except BudgetExceeded as failure:
                    failure.charged_tokens += charged
                    raise
            except (urllib.error.URLError, TimeoutError, OSError):
                self._emit({"type": "api_error", "error_type": "transport", "attempt": attempt + 1})
                if attempt == self.config.max_retries:
                    raise APIRequestError("API transport retries exhausted", charged_tokens=charged, reason='transport_retries_exhausted') from None
                delay = retry_delay(None, attempt + 1)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                self._emit({'type':'api_malformed_response','error_type':type(exc).__name__})
                raise APIRequestError("Malformed API response; any known usage settled, unknown reservation retained", charged_tokens=charged, reason='malformed_response') from None
            if deadline is not None and time.monotonic() + delay >= deadline:
                raise BudgetExceeded("Retry would exceed episode deadline", kind='time_limit', charged_tokens=charged)
            self._emit({"type": "api_retry_wait", "seconds": delay})
            self.sleep(delay)
        raise LLMError("Retry loop exhausted")
