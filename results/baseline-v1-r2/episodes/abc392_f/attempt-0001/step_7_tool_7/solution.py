#!/usr/bin/env python3
import sys
import json

class Fenwick:
    def __init__(self, n: int):
        self.n = n
        self.bit = [0] * (n + 1)
        # Build BIT with all ones (empty slots)
        for i in range(1, n + 1):
            self.bit[i] += 1
            j = i + (i & -i)
            if j <= n:
                self.bit[j] += self.bit[i]

    def sum(self, i: int) -> int:
        s = 0
        while i > 0:
            s += self.bit[i]
            i -= i & -i
        return s

    def add(self, i: int, delta: int) -> None:
        # Standard Fenwick update: include the last index
        while i <= self.n:
            self.bit[i] += delta
            i += i & -i

    def find_kth(self, k: int) -> int:
        """Return the smallest index such that prefix sum >= k."""
        idx = 0
        bit_mask = 1 << (self.n.bit_length() - 1)
        while bit_mask:
            t = idx + bit_mask
            if t <= self.n and self.bit[t] < k:
                idx = t
                k -= self.bit[t]
            bit_mask >>= 1
        return idx + 1


def solve(data: dict):
    positions = data["positions"]
    n = len(positions)
    res = [0] * n
    ft = Fenwick(n)
    # Process from largest number to smallest
    for i in range(n, 0, -1):
        p = positions[i - 1]
        idx = ft.find_kth(p)
        res[idx - 1] = i
        ft.add(idx, -1)
    return res

if __name__ == "__main__":
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)
    data = json.loads(raw)
    out = solve(data)
    sys.stdout.write(json.dumps(out))
