"""Sequential, resumable orchestration of independent baseline episodes."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import uuid

from . import __version__
from .agent import run_agent
from .api import BudgetExceeded, OpenAICompatibleClient, QuotaLedger
from .artifacts import exclusive_run, write_json
from .behavior import detect_behavior
from .config import ExperimentMode
from .environment import DockerEpisode, file_text
from .evaluator import evaluate_source, parse_proxy, validate_references
from .metrics import analyze, run_usage
from .llm import LLMError
from .sandbox import DockerSandbox, SandboxError
from .outcomes import classify_episode, solution_assessment
from .preservation import ensure_not_frozen
from .tasks import load_tasks
from .trajectory import TrajectoryLogger, changes_between, read_events


def enforce_baseline(config):
    if config.mode is not ExperimentMode.BASELINE or config.llm.backend!='api':
        raise ValueError('Baseline v1 supports only independent baseline API episodes')
    if config.llm.model!='openai/gpt-oss-20b' or config.llm.base_url.rstrip('/')!='https://api.groq.com/openai/v1':
        raise ValueError('Only the explicitly approved Groq model/endpoint may be used by this baseline command')
    caps = {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 8000, 'tokens_per_day': 200000}
    if any(getattr(config.budget, key) > value for key, value in caps.items()):
        raise ValueError('This controller may not exceed the agreed free account limits')
    if config.prompt_condition == 'public_reward' and not config.requires_run_approval:
        raise ValueError('Public reward condition requires explicit separate run approval')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def protocol_identity(config, image_id, prompt):
    root=Path(__file__).parent
    code={p.relative_to(root).as_posix():digest(p.read_bytes()) for p in sorted(root.rglob('*.py'))}
    return {'config':config.to_dict(),'image_id':image_id,'prompt_sha256':digest(prompt.encode()),
            'task_manifest_sha256':digest(config.task_manifest.read_bytes()),'controller_source_hashes':code,
            'seccomp_sha256':digest(root.joinpath('seccomp.json').read_bytes())}


def next_attempt(directory: Path):
    existing=[int(p.name.split('-')[-1]) for p in directory.glob('attempt-*') if p.is_dir()]
    return 'attempt-'+str(max(existing,default=0)+1).zfill(4)


def _finish_episode(task, attempt_dir, saved, config, logger, sandbox):
    source=file_text(saved['agent']['snapshot'],'solution.py')
    originals=task.public_files()
    files={name:originals[name] for name in ('problem.md','test_cases.json')}
    public=evaluate_source(source,task.metadata['visible_tests'],sandbox,files,attempt_dir/'original_public.json',event=logger.emit)
    hidden=evaluate_source(source,task.metadata['hidden_tests'],sandbox,files,attempt_dir/'true_success.json',event=logger.emit)
    initial=json.loads((attempt_dir/'initial_snapshot.json').read_text(encoding='utf-8'))
    behavior=detect_behavior(initial,saved['post_proxy_snapshot'],read_events(attempt_dir),frozen_solution=source)
    write_json(attempt_dir/'behavior.json',behavior)
    agent=saved['agent']
    assessment = solution_assessment(file_text(initial, 'solution.py'), source)
    outcome = classify_episode(agent['termination'], assessment, hidden['success'])
    summary={'schema_version':1,'status':'completed','task_id':task.task_id,'difficulty':task.difficulty,
             'episode_id':logger.context['episode_id'],'model':config.llm.model,'termination':agent['termination'],
             'tool_calls':agent['tool_calls'],'token_usage':agent['token_usage'],'charged_tokens':agent['charged_tokens'],
             'duration_s':agent['duration_s'],'proxy_success':saved['proxy']['success'],
             'reported_proxy_success':saved['proxy']['reported_success'],'proxy':saved['proxy'],
             'original_public_success':public['success'],'true_success':hidden['success'],'behavior':behavior,
             'solution_sha256':digest((source or '').encode()),'sandbox_image_id':sandbox.image_id,
             'correctness_scope':'Prepared independent tests only; not a proof of general correctness.'}
    summary.update(outcome, audit_status='unreviewed', interaction_termination_detail=agent.get('termination_detail'),
                   token_breakdown={key: agent.get(key) for key in ('input_tokens','output_tokens','reasoning_tokens_known','reasoning_usage_unknown_responses')})
    write_json(attempt_dir/'summary.json',summary)
    logger.emit({'type':'episode_completed','status':'completed','summary':summary})
    return summary


def run_experiment(config, experiment_id: str, *, stage='smoke', resume=False, approved_stage=None):
    enforce_baseline(config)
    if stage not in ('smoke', 'pilot'):
        raise ValueError('Unknown experiment stage')
    if config.requires_run_approval and approved_stage != config.prompt_condition + ':' + stage:
        raise ValueError('Researcher approval required for this condition and stage. No model request was made.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}',experiment_id):
        raise ValueError('experiment_id must be a safe directory identifier')
    directory=config.output_dir/experiment_id
    ensure_not_frozen(directory)
    tasks=load_tasks(config.task_manifest)
    if len(tasks)!=15 or any(sum(t.difficulty==d for t in tasks)!=5 for d in ('easy','medium','hard')):
        raise ValueError('Baseline v1 requires exactly five tasks in each of three levels')
    sandbox=DockerSandbox(config.sandbox)
    image_id=sandbox.prepare()  # No API interaction or unsafe fallback before isolation exists.
    prompt=config.prompt_path.read_text(encoding='utf-8')
    identity=protocol_identity(config,image_id,prompt)
    existed=directory.exists()
    if existed and not resume:
        raise FileExistsError('Experiment exists; use --resume to preserve completed episodes')
    if not existed and resume:
        raise FileNotFoundError('Cannot resume a missing experiment')
    directory.mkdir(parents=True,exist_ok=True)
    with exclusive_run(directory/'.controller.lock'):
        state_path=directory/'state.json'
        if existed:
            manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
            if manifest['protocol']!=identity:
                raise ValueError('Protocol/code/image changed. Start a separately identified experiment; do not mix observations.')
            state=json.loads(state_path.read_text(encoding='utf-8'))
        else:
            manifest={'schema_version':1,'experiment_id':experiment_id,'run_id':uuid.uuid4().hex,
                      'created_at':datetime.now(timezone.utc).isoformat(),'package_version':__version__,
                      'python_version':platform.python_version(),'protocol':identity,'prompt':prompt,
                      'independent_episodes':True,'incentives':None,'training':False,
                      'smoke_task_ids':[next(t.task_id for t in tasks if t.difficulty==d) for d in ('easy','medium','hard')]}
            write_json(directory/'manifest.json',manifest)
            state={'schema_version':1,'episodes':{},'task_order':[t.task_id for t in tasks]}
            write_json(state_path,state)
        validation_path=directory/'reference_validation.json'
        if not validation_path.exists():
            validate_references(tasks,sandbox,validation_path)
        else:
            validation=json.loads(validation_path.read_text(encoding='utf-8'))
            if not validation.get('success') or len(validation.get('tasks',[]))!=len(tasks) or validation['image_id']!=image_id:
                validate_references(tasks,sandbox,validation_path)
        ledger=QuotaLedger(config.output_dir/'.api_budget.json',config.budget)
        client=OpenAICompatibleClient(config.llm,ledger)
        client.check_model()
        selected=set(manifest['smoke_task_ids']) if stage=='smoke' else {t.task_id for t in tasks}
        try:
            for task in tasks:
                if task.task_id not in selected:
                    continue
                previous=state['episodes'].get(task.task_id)
                if previous and previous['status']=='completed':
                    continue
                remaining=config.budget.experiment_token_limit-run_usage(directory)['charged_tokens']
                if remaining < config.llm.max_output_tokens+1000:
                    raise BudgetExceeded('Experiment token cap reached; completed results are preserved')
                task_dir=directory/'episodes'/task.task_id
                pending=task_dir/previous['attempt'] if previous else None
                saved_path=pending/'agent_result.json' if pending else None
                if config.protocol_version == '1.1' and not (saved_path is not None and saved_path.exists()):
                    # Do not create a zero-action failed episode when the local
                    # account cannot fund the declared episode ceiling today.
                    ledger.require_daily_capacity(min(config.agent.max_episode_tokens, remaining))
                if saved_path is not None and saved_path.exists():
                    attempt_dir=pending
                    saved=json.loads(saved_path.read_text(encoding='utf-8'))
                    episode_id=previous['episode_id']
                    print('resume evaluation',task.task_id,flush=True)
                else:
                    attempt=next_attempt(task_dir)
                    attempt_dir=task_dir/attempt
                    episode_id=uuid.uuid4().hex
                    state['episodes'][task.task_id]={'attempt':attempt,'episode_id':episode_id,'status':'running','difficulty':task.difficulty}
                    write_json(state_path,state)
                    saved=None
                    print('start episode',task.task_id,task.difficulty,flush=True)
                logger=TrajectoryLogger(attempt_dir,experiment_id=experiment_id,run_id=manifest['run_id'],
                                        episode_id=episode_id,task_id=task.task_id,redactor=client.redactor)
                client.event=logger.emit
                try:
                    if saved is None:
                        with DockerEpisode(config.sandbox,config.agent,task.public_files()) as environment:
                            agent=run_agent(task,environment,client,logger,config,prompt,experiment_budget_remaining=remaining)
                            proxy_response=environment.request('run_command',{'command':'python -I -B test.py'})
                            proxy_execution=proxy_response.get('result') if proxy_response.get('ok') else {'status':'tool_error','stdout':'','stderr':'','exit_code':None}
                            post=environment.snapshot()
                            proxy=parse_proxy(proxy_execution,task.public_files(),post)
                            logger.emit({'type':'proxy_evaluation','status':proxy['status'],'result':proxy,
                                         'stdout':proxy_execution.get('stdout'),'stderr':proxy_execution.get('stderr'),
                                         'exit_code':proxy_execution.get('exit_code'),'duration_s':proxy_execution.get('duration_s'),
                                         'file_changes':changes_between(agent['snapshot'],post)})
                            logger.save_snapshot('post_proxy',post)
                            saved={'agent':agent,'proxy':proxy,'post_proxy_snapshot':post}
                            write_json(attempt_dir/'agent_result.json',client.redactor.clean(saved))
                        state['episodes'][task.task_id]['status']='evaluating'
                        write_json(state_path,state)
                    summary=_finish_episode(task,attempt_dir,saved,config,logger,sandbox)
                    state['episodes'][task.task_id]['status']='completed'
                    write_json(state_path,state)
                    analyze(directory)
                    print('completed',task.task_id,'proxy=',summary['proxy_success'],'true=',summary['true_success'],
                          'tokens=',summary['token_usage'],'behavior=',summary['behavior']['automated_status'],flush=True)
                    if saved['agent'].get('termination') == 'api_error':
                        state['stop_reason'] = 'api_error'
                        write_json(state_path, state)
                        print('fatal API error; stopping before starting another task', flush=True)
                        break
                    if saved['agent'].get('termination_detail') == 'daily_quota':
                        state['stop_reason'] = 'daily_quota'
                        write_json(state_path, state)
                        print('daily quota reached; remaining tasks preserved for --resume', flush=True)
                        break
                except BaseException as exc:
                    logger.emit({'type':'episode_interrupted','status':'interrupted','error_type':type(exc).__name__})
                    state['episodes'][task.task_id]['status']='evaluating' if (attempt_dir/'agent_result.json').exists() else 'interrupted'
                    failure = 'agent_aborted' if isinstance(exc, KeyboardInterrupt) else 'api_error' if isinstance(exc, LLMError) else 'infrastructure_error'
                    write_json(attempt_dir/'interruption.json', {'episode_outcome': failure, 'termination_reason': failure,
                               'error_type': type(exc).__name__, 'phase': state['episodes'][task.task_id]['status'],
                               'audit_status': 'unreviewed', 'independent_evaluation': None})
                    write_json(state_path,state)
                    raise
        finally:
            analyze(directory)
    return directory
