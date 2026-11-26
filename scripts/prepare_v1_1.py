"""Rebuild Stage A reports without initializing any LLM client."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from safety_games.archive import check_git_history
from safety_games.artifacts import write_json
from safety_games.config import load_config
from safety_games.preservation import verify_preservation
from safety_games.review import prepare_review
from safety_games.task_review import profile_tasks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('results/baseline-v1-r2'))
    parser.add_argument('--output',type=Path,default=Path('results/baseline-v1.1-preparation'))
    args=parser.parse_args()
    preservation=args.output/'preservation_manifest.json'
    if not preservation.exists():
        raise SystemExit('A pre-change preservation manifest is required; refusing to invent a historical baseline')
    verification=verify_preservation(preservation)
    if not verification['success']:
        raise SystemExit('Frozen data verification failed')
    write_json(args.output/'preservation_verification.json',verification)
    review=prepare_review(args.source,args.output/'review')
    profiles=profile_tasks('data/manifest.json',args.output/'tasks')
    old=load_config('configs/baseline_v1.toml').to_dict()
    new=load_config('configs/baseline_v1_1.toml').to_dict()
    changes=[]
    def compare(a,b,prefix=''):
        for key in sorted(set(a)|set(b)):
            name=prefix+key
            if isinstance(a.get(key),dict) and isinstance(b.get(key),dict):compare(a[key],b[key],name+'.')
            elif a.get(key)!=b.get(key):changes.append({'parameter':name,'old':a.get(key),'proposed':b.get(key)})
    compare(old,new)
    write_json(args.output/'config_comparison.json',{'old_config':old,'proposed_config':new,'changes':changes})
    security={'env_ignored':'.env' in Path('.gitignore').read_text(encoding='utf-8').splitlines(),
              'git':check_git_history(Path.cwd()),'no_live_llm_requests_in_stage_a':True,
              'note':'Key rotation does not reset the account ledger. Availability of the new key is intentionally not probed.'}
    write_json(args.output/'security_checks.json',security)
    write_json(args.output/'stage_a_summary.json',{'review':review,'tasks':len(profiles),'constraint_violations':sum(len(p['constraint_violations']) for p in profiles),
               'preservation':verification,'security':security,'smoke_performed':False,'pilot_performed':False,
               'judge_requests':0,'new_llm_requests':0})
    print(json.dumps({'reviewed_artifacts':review['episodes'],'preserved_files':verification['checked_files'],
                      'task_constraints_valid':all(not p['constraint_violations'] for p in profiles),'new_llm_requests':0}))


if __name__=='__main__':main()
