import json
import sys


def solve(data):
    """Return True if there are any duplicate integers in data["nums"]."""
    nums = data.get("nums", [])
    seen = set()
    for x in nums:
        if x in seen:
            return True
        seen.add(x)
    return False


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
