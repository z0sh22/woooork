#!/usr/bin/env python3
import sys
import json

sys.setrecursionlimit(10**7)

def longest_increasing_path(matrix):
    if not matrix or not matrix[0]:
        return 0
    rows, cols = len(matrix), len(matrix[0])
    memo = [[0]*cols for _ in range(rows)]
    dirs = [(1,0),(-1,0),(0,1),(0,-1)]

    def dfs(r,c):
        if memo[r][c]:
            return memo[r][c]
        best = 1
        for dr,dc in dirs:
            nr, nc = r+dr, c+dc
            if 0 <= nr < rows and 0 <= nc < cols and matrix[nr][nc] > matrix[r][c]:
                best = max(best, 1 + dfs(nr,nc))
        memo[r][c] = best
        return best

    ans = 0
    for i in range(rows):
        for j in range(cols):
            ans = max(ans, dfs(i,j))
    return ans

if __name__ == "__main__":
    data = json.load(sys.stdin)
    matrix = data.get("matrix", [])
    result = longest_increasing_path(matrix)
    json.dump(result, sys.stdout)
    sys.stdout.flush()
