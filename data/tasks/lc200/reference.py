import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    grid = data['grid']
    rows, cols = len(grid), len(grid[0])
    seen, result = set(), 0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != '1' or (r, c) in seen:
                continue
            result += 1
            seen.add((r, c))
            stack = [(r, c)]
            while stack:
                a, b = stack.pop()
                for x, y in ((a-1, b), (a+1, b), (a, b-1), (a, b+1)):
                    if 0 <= x < rows and 0 <= y < cols and grid[x][y] == '1' and (x, y) not in seen:
                        seen.add((x, y))
                        stack.append((x, y))
    return result


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
