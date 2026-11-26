"""Scan staged blobs and all reachable local history without printing secrets."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile
import io

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from safety_games.archive import _excluded, _local_secrets, contains_secret, check_git_history
from safety_games.artifacts import write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('results/baseline-v1.1-preparation/git_secret_scan.json'))
    args=parser.parse_args()
    def git(*args,input=None):
        result=subprocess.run(['git',*args],input=input,capture_output=True,timeout=60)
        if result.returncode:raise SystemExit('Git inspection failed; no secret values printed')
        return result.stdout
    root=Path(git('rev-parse','--show-toplevel').decode('utf-8').strip())
    secrets=_local_secrets(root)
    blobs={}
    excluded=[]
    staged=git('ls-files','--stage','-z').split(b'\0')
    for entry in staged:
        if not entry:continue
        header,name=entry.split(b'\t',1)
        mode,sha,stage=header.decode().split()
        name=name.decode('utf-8')
        frozen_zip = name == 'results/protocol_archives/r2-source.zip'
        if _excluded(PurePosixPath(name)) and not frozen_zip:excluded.append(name)
        blobs.setdefault(sha,name)
    historical={}
    for entry in git('rev-list','--objects','--all').splitlines():
        parts=entry.split(b' ',1)
        historical[parts[0].decode()]=parts[1].decode('utf-8') if len(parts)>1 else '<historical blob>'
    if historical:
        types=git('cat-file','--batch-check=%(objectname) %(objecttype)',input=('\n'.join(historical)+'\n').encode())
        for line in types.decode().splitlines():
            sha,kind=line.split()
            if kind=='blob':blobs.setdefault(sha,historical[sha])
    matches=[]
    if blobs:
        raw=git('cat-file','--batch',input=('\n'.join(blobs)+'\n').encode())
        offset=0
        for sha,name in blobs.items():
            end=raw.index(b'\n',offset)
            got,kind,size=raw[offset:end].decode().split()
            if got!=sha or kind!='blob':raise SystemExit('Unexpected Git batch response')
            start=end+1;offset=start+int(size)+1
            content = raw[start:offset-1]
            if contains_secret(content,secrets):matches.append(name)
            if name == 'results/protocol_archives/r2-source.zip':
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    for info in archive.infolist():
                        if info.file_size > 32*1024*1024 or contains_secret(archive.read(info),secrets):
                            matches.append(name+':'+info.filename)
    history=check_git_history(root)
    success=not matches and not excluded and not history.get('env_tracked') and not history.get('env_in_history')
    report={'success':success,'staged_or_historical_blobs_checked':len(blobs),'potential_secret_paths':matches,
            'excluded_paths_staged':excluded,'git':history,'secret_values_printed':False,
            'scope':'Current configured secret, common token/private-key patterns and encoded snapshots; not arbitrary unknown secret formats.'}
    write_json(args.output,report)
    print(json.dumps(report,ensure_ascii=True))
    return 0 if success else 1


if __name__=='__main__':raise SystemExit(main())
