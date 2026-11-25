import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    from collections import deque
    matrix = data['matrix']
    n, m = len(matrix), len(matrix[0])
    degree = [[0]*m for _ in range(n)]
    queue = deque()
    for r in range(n):
        for c in range(m):
            degree[r][c] = sum(0 <= a < n and 0 <= b < m and matrix[a][b] < matrix[r][c]
                               for a, b in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)))
            if not degree[r][c]:
                queue.append((r, c))
    layers = 0
    while queue:
        layers += 1
        for _ in range(len(queue)):
            r, c = queue.popleft()
            for a, b in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                if 0 <= a < n and 0 <= b < m and matrix[a][b] > matrix[r][c]:
                    degree[a][b] -= 1
                    if not degree[a][b]:
                        queue.append((a, b))
    return layers


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
