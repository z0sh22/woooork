"""Trusted transport bootstrap. Run ONLY inside the restricted container."""

import json
import os
from pathlib import Path
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    source = payload["source"]
    input_text = payload["stdin"]
    if not isinstance(source, str) or not isinstance(input_text, str):
        raise TypeError("source and stdin must be strings")
    for name, text in payload.get('files', {}).items():
        if name not in ('test_cases.json', 'problem.md') or not isinstance(text, str):
            raise ValueError('invalid public file')
        Path('/tmp', name).write_text(text, encoding='utf-8')
    Path("/tmp/solution.py").write_text(source, encoding="utf-8")
    # A file gives user code normal stdin semantics after the transport is read.
    with open("/tmp/input.txt", "w+b") as input_file:
        input_file.write(input_text.encode("utf-8"))
        input_file.seek(0)
        os.dup2(input_file.fileno(), 0)
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"}
    os.execve(sys.executable, [sys.executable, "-I", "-B", "/tmp/solution.py"], environment)


if __name__ == "__main__":
    main()
