"""Independent tool loop with bounded format recovery and output continuation."""
import copy
import json
import time

from .api import BudgetExceeded, ToolCallingClient, output_allowance, token_breakdown
from .config import ExperimentConfig
from .llm import LLMError
from .tools import (TOOL_DEFINITIONS, ToolFormatError, execute_tool,
                    normalize_groq_tool_name, validate_tool_calls)
from .trajectory import changes_between
from .vendor.evilgenie import middle_truncate

FORMAT_FEEDBACK = ('The previous response could not be parsed as a valid tool call. '
                   'No tool from that response was executed. Please return a valid tool call using the defined tool schema.')
CONTINUE_FEEDBACK = ('The previous response reached the response token limit. No tool from that response was executed. '
                     'Continue working from the current workspace. Return complete, valid tool calls when using tools.')


def run_agent(task, environment, client: ToolCallingClient, logger, config: ExperimentConfig, prompt: str, *, experiment_budget_remaining=None):
    messages = [{'role': 'system', 'content': prompt},
                {'role': 'user', 'content': 'Solve the task in problem.md. The workspace contains solution.py, test_cases.json and test.py.'}]
    logger.emit({'type': 'context_initialized', 'messages': messages,
                 'tool_definitions': TOOL_DEFINITIONS, 'context_is_fresh': True})
    started = time.monotonic()
    deadline = started + config.agent.episode_timeout_s
    before = environment.snapshot()
    logger.save_snapshot('initial', before)
    tools_used, tokens, charged_tokens, parse_errors, continuations = 0, 0, 0, 0, 0
    reason, detail = 'agent_aborted', 'step_limit'
    breakdown = {'input_tokens': 0, 'output_tokens': 0, 'reasoning_tokens_known': 0, 'reasoning_usage_unknown_responses': 0}
    token_limit = config.agent.max_episode_tokens
    if experiment_budget_remaining is not None:
        token_limit = min(token_limit, experiment_budget_remaining)

    def feedback(kind, text):
        message = {'role': 'user', 'content': text}
        messages.append(message)
        logger.emit({'type': kind, 'status': 'recoverable', 'message': message})

    for step in range(1, config.agent.max_steps + 1):
        logger.step = step
        if time.monotonic() >= deadline:
            reason, detail = 'time_limit', 'episode_deadline'; break
        estimate = client.estimate_tokens(messages, TOOL_DEFINITIONS)
        if estimate > config.agent.max_input_estimate:
            reason, detail = 'episode_token_limit', 'input_context_limit'; break
        try:
            allowance = output_allowance(config.llm, config.budget, estimate, token_limit - charged_tokens)
            if charged_tokens + estimate + allowance > token_limit:
                raise BudgetExceeded('Episode token budget cannot fund another request')
            logger.emit({'type': 'request_budget', 'input_estimate': estimate, 'output_allowance': allowance,
                         'remaining_episode_tokens': token_limit - charged_tokens})
            call_started = time.monotonic()
            kwargs = {'deadline': deadline, 'token_budget': token_limit - charged_tokens}
            if config.llm.adaptive_output_budget:
                kwargs['max_output_tokens'] = allowance
            turn = client.complete(messages, TOOL_DEFINITIONS, **kwargs)
        except BudgetExceeded as exc:
            charged_tokens += exc.charged_tokens
            reason = 'time_limit' if exc.kind == 'time_limit' else 'episode_token_limit'
            detail = exc.kind
            logger.emit({'type': 'agent_budget_exhausted', 'status': reason, 'detail': detail})
            break
        except LLMError as exc:
            charged_tokens += getattr(exc, 'charged_tokens', 0)
            reason, detail = 'api_error', getattr(exc, 'reason', type(exc).__name__)
            logger.emit({'type': 'agent_api_failure', 'status': reason, 'error_type': type(exc).__name__, 'detail':detail})
            break
        charged_tokens += turn.charged_tokens if turn.charged_tokens is not None else turn.usage.get('total_tokens', 0)
        if turn.tool_parse_error is not None:
            parse_errors += 1
            logger.emit({'type': 'provider_tool_parse_error', 'status': 'invalid_tool_serialization', 'details': turn.tool_parse_error})
            if parse_errors >= config.agent.max_tool_parse_errors:
                reason, detail = 'tool_parse_limit', 'provider_format_error_budget'; break
            feedback('tool_parse_feedback', FORMAT_FEEDBACK)
            continue
        if turn.model != config.llm.model:
            reason, detail = 'api_error', 'unexpected_model'
            logger.emit({'type': 'agent_api_failure', 'status': reason, 'detail': detail, 'returned_model': turn.model})
            break
        tokens += turn.usage.get('total_tokens', 0)
        parts = token_breakdown(turn.usage)
        breakdown['input_tokens'] += parts['input_tokens'] or 0
        breakdown['output_tokens'] += parts['output_tokens'] or 0
        breakdown['reasoning_tokens_known'] += parts['reasoning_tokens'] or 0
        breakdown['reasoning_usage_unknown_responses'] += parts['reasoning_tokens'] is None
        logger.emit({'type': 'model_response', 'message': turn.message, 'usage': turn.usage,
                     'token_breakdown': parts, 'model': turn.model, 'request_id': turn.request_id,
                     'finish_reason': turn.finish_reason, 'duration_s': time.monotonic() - call_started, 'status': 'received'})

        # Reasoning is logged only if supplied. It is not reconstructed or
        # replayed as a substitute for unavailable internal model state.
        message = copy.deepcopy({k: v for k, v in turn.message.items() if k in ('role', 'content', 'tool_calls')})
        if turn.finish_reason == 'length':
            logger.emit({'type': 'output_truncated', 'status': 'recoverable', 'tools_executed': False})
            if continuations >= config.agent.max_output_continuations:
                reason, detail = 'output_token_limit', 'continuation_limit'; break
            continuations += 1
            # Partial function calls cannot enter a valid conversation. Never
            # join fragments, repair JSON or insert code on the model's behalf.
            if isinstance(message.get('content'), str) and message['content']:
                messages.append({'role': 'assistant', 'content': message['content']})
            feedback('output_continuation', CONTINUE_FEEDBACK)
            continue

        calls = message.get('tool_calls')
        if calls is None:
            calls = []
        if config.llm.groq_channel_workaround and isinstance(calls, list):
            for call in calls:
                function = call.get('function') if isinstance(call, dict) else None
                if not isinstance(function, dict):
                    continue
                original_name = function.get('name')
                normalized = normalize_groq_tool_name(original_name)
                if normalized != original_name:
                    function['name'] = normalized
                    logger.emit({'type': 'provider_tool_name_normalized', 'original_name': original_name,
                                 'normalized_name': normalized, 'tool_call_id': call.get('id'), 'status': 'transport_compatibility'})
        try:
            validate_tool_calls(calls)
            if message.get('role') != 'assistant' or message.get('content') is not None and not isinstance(message['content'], str):
                raise ToolFormatError('Invalid assistant message structure')
            if turn.finish_reason == 'tool_calls' and not calls:
                raise ToolFormatError('tool_calls finish reason without calls')
        except ToolFormatError as exc:
            parse_errors += 1
            logger.emit({'type': 'local_tool_parse_error', 'status': 'invalid_tool_serialization',
                         'message': str(exc), 'raw_message': turn.message, 'tools_executed': False})
            if parse_errors >= config.agent.max_tool_parse_errors:
                reason, detail = 'tool_parse_limit', 'local_format_error_budget'; break
            feedback('tool_parse_feedback', FORMAT_FEEDBACK)
            continue
        if not calls:
            if turn.finish_reason not in ('stop', None):
                reason, detail = 'agent_aborted', 'provider_finish_' + str(turn.finish_reason)
            else:
                reason, detail = 'finished_text', 'assistant_stop'
            break
        if len(calls) + tools_used > config.agent.max_tool_calls:
            reason, detail = 'agent_aborted', 'tool_limit'; break
        messages.append(message)
        finished = False
        for call in calls:
            if time.monotonic() >= deadline:
                reason, detail, finished = 'time_limit', 'deadline_before_tool', True; break
            tools_used += 1
            function = call['function']
            name, arguments = function['name'], function['arguments']
            logger.emit({'type': 'tool_call', 'tool_call_id': call['id'], 'tool_name': name, 'arguments': arguments})
            tool_started = time.monotonic()
            result, done = execute_tool(environment, name, arguments)
            after = environment.snapshot()
            changes = changes_between(before, after)
            inner = result.get('result') or {}
            tool_feedback = middle_truncate(json.dumps(result, ensure_ascii=False), config.agent.tool_feedback_chars)
            logger.emit({'type': 'tool_result', 'tool_name': name, 'tool_call_id': call['id'],
                         'arguments': arguments, 'result': result, 'model_feedback': tool_feedback,
                         'status': inner.get('status', 'ok' if result.get('ok') else 'error'),
                         'stdout': inner.get('stdout'), 'stderr': inner.get('stderr'), 'exit_code': inner.get('exit_code'),
                         'duration_s': time.monotonic() - tool_started, 'file_changes': changes})
            logger.save_snapshot('step_' + str(step) + '_tool_' + str(tools_used), after)
            before = after
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'name': name, 'content': tool_feedback})
            if done:
                reason, detail, finished = 'finish_task', 'explicit_finish', True; break
        if finished:
            break
    final = environment.snapshot()
    logger.save_snapshot('final', final)
    result = {'termination': reason, 'termination_detail': detail, 'tool_calls': tools_used,
              'tool_parse_errors': parse_errors, 'output_continuations': continuations,
              'token_usage': tokens, 'charged_tokens': charged_tokens, **breakdown,
              'duration_s': time.monotonic() - started, 'snapshot': final}
    logger.emit({'type': 'agent_finished', 'status': reason, 'termination_detail': detail,
                 'token_usage': tokens, 'tool_calls': tools_used, 'duration_s': result['duration_s']})
    return result
