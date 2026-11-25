import json
import sys


def find_kth(a, b, k):
    """Return the k-th smallest element (0-indexed) in the union of sorted lists a and b."""
    # Ensure a is the shorter list
    if len(a) > len(b):
        return find_kth(b, a, k)
    m, n = len(a), len(b)
    # Edge cases
    if m == 0:
        return b[k]
    if k == 0:
        return a[0] if a[0] < b[0] else b[0]
    # Binary search on a
    left, right = 0, min(m, k)
    while left <= right:
        i = (left + right) // 2
        j = k - i
        a_left = a[i - 1] if i > 0 else float('-inf')
        a_right = a[i] if i < m else float('inf')
        b_left = b[j - 1] if j > 0 else float('-inf')
        b_right = b[j] if j < n else float('inf')
        if a_left <= b_right and b_left <= a_right:
            return max(a_left, b_left)
        elif a_left > b_right:
            right = i - 1
        else:
            left = i + 1
    # Should not reach here
    raise ValueError("k out of bounds")


def solve(data):
    a = data.get("a", [])
    b = data.get("b", [])
    total = len(a) + len(b)
    if total == 0:
        raise ValueError("At least one array must be non-empty")
    if total % 2 == 1:
        k = total // 2
        median = find_kth(a, b, k)
        return median
    else:
        k1 = total // 2 - 1
        k2 = total // 2
        val1 = find_kth(a, b, k1)
        val2 = find_kth(a, b, k2)
        return (val1 + val2) / 2


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
