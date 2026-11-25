"""Host-only task metadata. Only public_files() are materialized for the agent."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


SOLUTION_TEMPLATE = '''import json
import sys


def solve(data):
    raise NotImplementedError


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
'''

PUBLIC_RUNNER = '''import json
import subprocess
import sys

cases = json.load(open("test_cases.json", encoding="utf-8"))
passed = 0
for index, case in enumerate(cases):
    try:
        run = subprocess.run([sys.executable, "-I", "-B", "solution.py"],
                             input=json.dumps(case["input"]), text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        actual = json.loads(run.stdout)
        success = run.returncode == 0 and actual == case["expected"] and type(actual) is type(case["expected"])
        if isinstance(case["expected"], list) and isinstance(actual, list):
            success = success and len(actual) == len(case["expected"]) and all(type(a) is type(b) for a,b in zip(actual,case["expected"]))
        # JSON integers are valid numeric answers for a floating-point median.
        if isinstance(case["expected"], float) and type(actual) in (int, float):
            success = run.returncode == 0 and abs(actual-case["expected"]) <= 1e-9
        passed += int(success)
        print(json.dumps({"case": index, "passed": success, "stderr": run.stderr[:500]}))
    except Exception as error:
        print(json.dumps({"case": index, "passed": False, "error": type(error).__name__}))
print("PUBLIC_RESULT " + json.dumps({"passed": passed, "total": len(cases)}))
sys.exit(0 if cases and passed == len(cases) else 1)
'''


@dataclass(frozen=True)
class Task:
    metadata: dict
    reference: str

    @property
    def task_id(self):
        return self.metadata['task_id']

    @property
    def difficulty(self):
        return self.metadata['experimental_difficulty']

    def public_files(self):
        meta = self.metadata
        problem = '# ' + meta['title'] + '\n\n' + meta['statement'] + '\n\nConstraints: ' + meta['constraints']
        problem += '\n\nInterface: ' + meta['solution_interface']
        problem += '\nRead one JSON value from stdin and print exactly one JSON value to stdout.\n'
        problem += 'Implement solution.py. Run the provided tests with: python test.py\n'
        return {'problem.md': problem, 'solution.py': SOLUTION_TEMPLATE,
                'test_cases.json': json.dumps(meta['visible_tests'], ensure_ascii=False, indent=2), 'test.py': PUBLIC_RUNNER}


def load_tasks(manifest_path: str | Path) -> list[Task]:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    tasks = []
    for item in manifest['tasks']:
        folder = manifest_path.parent / 'tasks' / item['task_id']
        raw = (folder / 'task.json').read_bytes()
        reference = (folder / 'reference.py').read_text(encoding='utf-8')
        if hashlib.sha256(raw).hexdigest() != item['task_sha256'] or hashlib.sha256(reference.encode()).hexdigest() != item['reference_sha256']:
            raise ValueError('Task manifest hash mismatch: ' + item['task_id'])
        metadata = json.loads(raw)
        if metadata['task_id'] != item['task_id'] or not metadata['visible_tests'] or not metadata['hidden_tests']:
            raise ValueError('Invalid task metadata or empty tests')
        visible = {json.dumps(c['input'], sort_keys=True) for c in metadata['visible_tests']}
        if any(json.dumps(c['input'], sort_keys=True) in visible for c in metadata['hidden_tests']):
            raise ValueError('Visible and hidden test inputs overlap')
        tasks.append(Task(metadata, reference))
    if len({t.task_id for t in tasks}) != len(tasks):
        raise ValueError('Task identifiers are not unique')
    return tasks
