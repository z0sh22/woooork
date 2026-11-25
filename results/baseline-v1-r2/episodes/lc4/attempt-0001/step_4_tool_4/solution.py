import json
import sys


def solve(data):
    raise NotImplementedError


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
