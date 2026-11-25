import json
import sys
from functools import lru_cache


def solve(data):
    s = data["s"]
    p = data["p"]
    n, m = len(s), len(p)

    @lru_cache(maxsize=None)
    def dp(i, j):
        # i: index in s, j: index in p
        if j == m:
            return i == n
        # check if next char is '*'
        if j + 1 < m and p[j + 1] == '*':
            # zero occurrence
            if dp(i, j + 2):
                return True
            # one or more occurrences
            if i < n and (p[j] == s[i] or p[j] == '.'):
                return dp(i + 1, j)
            return False
        else:
            if i < n and (p[j] == s[i] or p[j] == '.'):
                return dp(i + 1, j + 1)
            return False

    return dp(0, 0)


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
