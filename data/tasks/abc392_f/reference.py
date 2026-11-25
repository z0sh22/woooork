import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    positions = data['positions']
    n = len(positions)
    tree, result = [0]*(n+1), [0]*n
    for index in range(1, n+1):
        tree[index] = index & -index
    for value in range(n, 0, -1):
        rank, index, bit = positions[value-1], 0, 1 << (n.bit_length()-1)
        while bit:
            nxt = index + bit
            if nxt <= n and tree[nxt] < rank:
                index = nxt
                rank -= tree[nxt]
            bit >>= 1
        result[index] = value
        update = index + 1
        while update <= n:
            tree[update] -= 1
            update += update & -update
    return result


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
