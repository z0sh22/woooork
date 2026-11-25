import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    last, left, best = {}, 0, 0
    for right, char in enumerate(data['s']):
        left = max(left, last.get(char, -1) + 1)
        last[char] = right
        best = max(best, right - left + 1)
    return best


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
