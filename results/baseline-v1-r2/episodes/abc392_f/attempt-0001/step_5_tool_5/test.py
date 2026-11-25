import json
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
