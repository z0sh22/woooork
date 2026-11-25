import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    prices, budget = data['prices'], data['budget']
    lo, hi = 0, budget + 1
    while lo + 1 < hi:
        threshold = (lo + hi) // 2
        count = [(threshold // p + 1) // 2 for p in prices]
        cost = sum(p*k*k for p, k in zip(prices, count))
        if cost <= budget:
            lo = threshold
        else:
            hi = threshold
    counts = [(lo // p + 1) // 2 for p in prices]
    spent = sum(p*k*k for p, k in zip(prices, counts))
    next_price = min(p*(2*k+1) for p, k in zip(prices, counts))
    return sum(counts) + (budget-spent) // next_price


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
