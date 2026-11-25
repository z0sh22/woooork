"""Run actual unittest checks and save machine-readable infrastructure evidence."""
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    output=io.StringIO()
    started=time.monotonic()
    suite=unittest.defaultTestLoader.discover('tests')
    result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    destination=Path('results/infrastructure_tests.json')
    destination.parent.mkdir(exist_ok=True)
    document={'kind':'infrastructure_tests_not_behavioral_data','tests_run':result.testsRun,
              'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
              'successful':result.wasSuccessful(),'duration_s':time.monotonic()-started,
              'python_version':platform.python_version(),'docker_tests_requested':os.environ.get('SAFETY_GAMES_DOCKER_TESTS')=='1',
              'details':output.getvalue()}
    destination.write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in document.items() if k!='details'}))
    if not result.wasSuccessful():print(output.getvalue())
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
