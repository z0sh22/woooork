import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    a, b = data['a'], data['b']
    if len(a) > len(b):
        a, b = b, a
    m, n = len(a), len(b)
    lo, hi = 0, m
    while lo <= hi:
        i = (lo + hi) // 2
        j = (m + n + 1) // 2 - i
        al, ar = a[i-1] if i else -float('inf'), a[i] if i < m else float('inf')
        bl, br = b[j-1] if j else -float('inf'), b[j] if j < n else float('inf')
        if al <= br and bl <= ar:
            return float(max(al, bl)) if (m+n) % 2 else (max(al, bl) + min(ar, br)) / 2
        if al > br:
            hi = i - 1
        else:
            lo = i + 1
    raise ValueError('unsorted input')


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
