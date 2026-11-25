"""Check persisted artifacts for the actual configured key without printing it."""
import base64
import json
import os
from pathlib import Path
import sys

from dotenv import dotenv_values


def main():
    key=os.environ.get('GROQ_API_KEY') or dotenv_values('.env',interpolate=False).get('GROQ_API_KEY')
    if not key:raise SystemExit('Configured key unavailable for artifact verification')
    secret=key.encode('utf-8')
    matches=[];scanned=0
    def inspect(value,path):
        if isinstance(value,dict):
            if value.get('kind')=='file' and value.get('encoding')=='base64':
                try:
                    if secret in base64.b64decode(value.get('content',''),validate=True):matches.append(str(path)+':encoded_snapshot')
                except ValueError:pass
            for item in value.values():inspect(item,path)
        elif isinstance(value,list):
            for item in value:inspect(item,path)
    for base in ('results','docs','safety_games','configs','data','prompts','sandbox','third_party','scripts','tests'):
        for path in Path(base).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix.lower() not in ('.json','.jsonl','.md','.csv','.py','.toml','.txt','.svg'):
                continue
            raw=path.read_bytes();scanned+=1
            if secret in raw:matches.append(str(path))
            if path.suffix=='.json':
                try:inspect(json.loads(raw),path)
                except ValueError:pass
    result={'actual_api_key_found_in_artifacts':bool(matches),'files_checked':scanned,'matching_paths':matches}
    Path('results/secret_scan.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 1 if matches else 0


if __name__=='__main__':raise SystemExit(main())
