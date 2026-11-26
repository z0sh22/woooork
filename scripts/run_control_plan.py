"""Authorized control smoke, gate, then pilot; wait rather than bypass quotas."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from safety_games.api import BudgetExceeded, OpenAICompatibleClient, QuotaLedger
from safety_games.artifacts import exclusive_run, write_json
from safety_games.config import load_config
from safety_games.experiment import enforce_baseline, protocol_identity, run_experiment
from safety_games.metrics import analyze
from safety_games.preservation import ensure_not_frozen, verify_preservation
from safety_games.sandbox import DockerSandbox


def smoke_gate(directory):
    """Gate on controller validity; model failures and tampering stay observations."""
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
    checks=[]
    for task_id in manifest['smoke_task_ids']:
        entry=state['episodes'].get(task_id,{})
        path=directory/'episodes'/task_id/entry.get('attempt','missing')/'summary.json'
        summary=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        checks.append({'task_id':task_id, 'completed':entry.get('status')=='completed',
                       'technically_completed':summary.get('technically_completed') is True,
                       'solution_written':summary.get('solution_written') is True,
                       'independent_evaluation_known':type(summary.get('true_success')) is bool,
                       'proxy_evaluation_recorded':isinstance(summary.get('proxy'),dict) and bool(summary['proxy'].get('status')),
                       'no_fatal_controller_error':summary.get('episode_outcome')!='infrastructure_error' and summary.get('termination_reason')!='api_error',
                       'snapshots_present':all((path.parent/(label+'_snapshot.json')).is_file() for label in ('initial','final','post_proxy')),
                       'has_model_usage':summary.get('token_usage',0)>0,
                       'termination':summary.get('termination_reason'), 'true_success':summary.get('true_success')})
    fields=('completed','independent_evaluation_known','proxy_evaluation_recorded','has_model_usage','snapshots_present','no_fatal_controller_error')
    return {'passed':all(all(c[k] for k in fields) for c in checks), 'checks':checks,
            'rule':'All three controller/evaluation pipelines complete with observations and no fatal API/infrastructure errors. No filtering by correctness, hacking, implementation presence or model budget termination.'}


def _requires_model(directory, stage):
    if not directory.exists():return True
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
    wanted=manifest['smoke_task_ids'] if stage=='smoke' else state['task_order']
    for task_id in wanted:
        entry=state['episodes'].get(task_id)
        if entry and entry['status']=='completed':continue
        saved=directory/'episodes'/task_id/entry['attempt']/'agent_result.json' if entry else None
        return saved is None or not saved.exists()
    return False


def run_plan(config_path, experiment_id, plan_dir, *, approved, max_wait_hours=24, poll_s=30):
    if not approved:
        raise ValueError('This command requires the researcher-approved control smoke and conditional pilot')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}',experiment_id):
        raise ValueError('Invalid experiment ID')
    if not math.isfinite(max_wait_hours) or max_wait_hours<0:
        raise ValueError('max_wait_hours must be a finite nonnegative duration')
    config=load_config(config_path)
    enforce_baseline(config)
    if config.protocol_version!='1.1' or config.prompt_condition!='control':
        raise ValueError('This plan permits only v1.1 control; no public-reward condition or judge')
    preservation=verify_preservation('results/baseline-v1.1-preparation/preservation_manifest.json')
    if not preservation['success']:
        raise ValueError('Frozen v1.0 verification failed')
    plan_dir=Path(plan_dir);ensure_not_frozen(plan_dir);plan_dir.mkdir(parents=True,exist_ok=True)
    directory=config.output_dir/experiment_id
    ledger=QuotaLedger(config.output_dir/'.api_budget.json',config.budget)
    image= DockerSandbox(config.sandbox).prepare()
    identity=protocol_identity(config,image,config.prompt_path.read_text(encoding='utf-8'))
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    runner_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    status_path=plan_dir/'status.json'
    started=time.monotonic()
    with exclusive_run(plan_dir/'.plan.lock'):
        previous=json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
        if previous and (previous['protocol_fingerprint']!=fingerprint or previous['runner_sha256']!=runner_hash):
            raise ValueError('Plan protocol/runner changed; use a new plan and experiment ID')
        status={'experiment_id':experiment_id,'protocol_fingerprint':fingerprint,'runner_sha256':runner_hash,
                'approval':'2026-11-26 user approved control smoke then 15-task pilot conditional on technical readiness and budget',
                'phase':previous.get('phase','smoke'),'state':'preflight','directory':str(directory),
                'public_reward_authorized':False,'judge_authorized':False,'pid':os.getpid()}
        def save(**values):
            status.update(values,updated_at_utc=datetime.now(timezone.utc).isoformat())
            write_json(status_path,status)
        try:
            client=OpenAICompatibleClient(config.llm,ledger)
            availability=client.check_model() # Read-only; no inference.
            save(model_preflight=availability)
            if previous.get('state') in ('completed','smoke_gate_failed'):
                save(state=previous['state']);return status
            for stage in ('smoke','pilot'):
                if stage=='smoke' and previous.get('phase')=='pilot':continue
                while True:
                    quota=ledger.daily_status(config.agent.max_episode_tokens)
                    if not quota['ready_now'] and _requires_model(directory,stage):
                        target=quota['ready_at_epoch']
                        ready=datetime.fromtimestamp(target,timezone.utc).isoformat() if target is not None else None
                        save(state='waiting_quota',phase=stage,quota=quota,earliest_local_ready_utc=ready)
                        if time.monotonic()-started >= max_wait_hours*3600:
                            save(state='wait_limit_reached');return status
                        time.sleep(min(max(1,poll_s),30))
                        continue
                    save(state='running',phase=stage,quota=quota,earliest_local_ready_utc=None)
                    current_image=DockerSandbox(config.sandbox).prepare()
                    current_identity=protocol_identity(config,current_image,config.prompt_path.read_text(encoding='utf-8'))
                    if current_identity!=identity or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=runner_hash:
                        raise ValueError('Protocol or image changed while waiting; refusing to mix versions')
                    try:
                        run_experiment(config,experiment_id,stage=stage,resume=directory.exists(),approved_stage='control:'+stage)
                    except BudgetExceeded as exc:
                        if exc.kind!='daily_quota':raise
                        continue
                    state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
                    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
                    wanted=manifest['smoke_task_ids'] if stage=='smoke' else state['task_order']
                    if any(state['episodes'].get(t,{}).get('status')!='completed' for t in wanted):
                        if state.get('stop_reason')=='daily_quota':continue
                        save(controller_stop_reason=state.get('stop_reason'))
                        raise ValueError('Incomplete run without a documented daily quota stop')
                    if stage=='smoke':
                        gate=smoke_gate(directory)
                        write_json(plan_dir/'smoke_gate.json',gate)
                        write_json(plan_dir/'smoke_checkpoint.json',analyze(directory))
                        if not gate['passed']:
                            save(state='smoke_gate_failed',smoke_gate=gate);return status
                    break
            save(state='completed',phase='pilot',completed_episodes=15)
        except BaseException as exc:
            # Never persist arbitrary exception text that may include secrets.
            save(state='failed',error_type=type(exc).__name__)
            raise
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/baseline_v1_1.toml')
    parser.add_argument('--experiment-id',required=True)
    parser.add_argument('--plan-dir',required=True)
    parser.add_argument('--approved-control-smoke-and-pilot',action='store_true')
    parser.add_argument('--max-wait-hours',type=float,default=24)
    args=parser.parse_args()
    result=run_plan(args.config,args.experiment_id,args.plan_dir,approved=args.approved_control_smoke_and_pilot,max_wait_hours=args.max_wait_hours)
    print(json.dumps(result,ensure_ascii=True))
    return 0 if result['state']=='completed' else 2


if __name__=='__main__':raise SystemExit(main())
