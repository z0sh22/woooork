import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    limit, foods = data['limit'], data['foods']
    tables = []
    for vitamin in (1, 2, 3):
        dp = [0] * (limit + 1)
        for v, amount, cost in foods:
            if v == vitamin:
                for capacity in range(limit, cost-1, -1):
                    dp[capacity] = max(dp[capacity], dp[capacity-cost] + amount)
        for capacity in range(1, limit+1):
            dp[capacity] = max(dp[capacity], dp[capacity-1])
        tables.append(dp)
    lo, hi = 0, min(t[-1] for t in tables) + 1
    while lo + 1 < hi:
        middle = (lo + hi) // 2
        cost = sum(bisect.bisect_left(table, middle) for table in tables)
        if cost <= limit:
            lo = middle
        else:
            hi = middle
    return lo


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
