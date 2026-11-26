"""Separate interaction termination, implementation evidence and correctness."""
import ast

OUTCOMES = ('success', 'incorrect_solution', 'unfinished_solution', 'output_token_limit',
            'episode_token_limit', 'tool_parse_limit', 'time_limit', 'api_error',
            'agent_aborted', 'infrastructure_error')

NORMAL_TERMINATIONS = frozenset(('finish_task', 'finished_text'))
TECHNICAL_TERMINATIONS = frozenset(OUTCOMES[3:])
LEGACY_TERMINATIONS = {'token_budget': 'episode_token_limit', 'context_budget': 'episode_token_limit',
                       'episode_timeout': 'time_limit', 'tool_limit': 'agent_aborted',
                       'step_limit': 'agent_aborted'}


def solution_assessment(original, final):
    """Static presence heuristic; does not assess algorithmic correctness."""
    if final is None:
        return {'solution_written': False, 'solution_state': 'missing_or_nonregular'}
    try:
        tree = ast.parse(final)
        old = ast.parse(original or '')
    except (SyntaxError, ValueError, RecursionError):
        return {'solution_written': False, 'solution_state': 'invalid_syntax'}
    if ast.dump(tree, include_attributes=False) == ast.dump(old, include_attributes=False):
        return {'solution_written': False, 'solution_state': 'unchanged_template'}
    placeholder = any(isinstance(n, ast.Raise) and
                      (isinstance(n.exc, ast.Name) and n.exc.id == 'NotImplementedError' or
                       isinstance(n.exc, ast.Call) and isinstance(n.exc.func, ast.Name) and n.exc.func.id == 'NotImplementedError')
                      for n in ast.walk(tree))
    substantive = any(isinstance(n, (ast.Return, ast.Assign, ast.AugAssign, ast.For, ast.While,
                                    ast.ListComp, ast.Call)) for n in ast.walk(tree))
    present = substantive and not placeholder
    return {'solution_written': present, 'solution_state': 'modified_implementation' if present else 'placeholder_or_empty'}


def classify_episode(termination, assessment, true_success):
    canonical = LEGACY_TERMINATIONS.get(termination, termination)
    technical = canonical not in NORMAL_TERMINATIONS
    if true_success is True:
        outcome = 'success'
    elif canonical in TECHNICAL_TERMINATIONS:
        outcome = canonical
    elif technical:
        outcome = 'agent_aborted'
    else:
        outcome = 'incorrect_solution' if assessment['solution_written'] else 'unfinished_solution'
    return {**assessment, 'termination_reason': canonical, 'termination_detail': termination,
            'technically_completed': not technical, 'episode_outcome': outcome}
