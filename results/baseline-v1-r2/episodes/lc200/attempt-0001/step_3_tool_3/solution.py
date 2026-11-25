#!/usr/bin/env python3
"""
Number of Islands
=================

The input is a JSON object with a single key ``grid`` that maps to a list of
binary strings.  Each string represents a row of a rectangular grid.  The
task is to count the number of connected components of the character ``"1"``.

Connectivity is 4‑way (up, down, left, right).  Diagonal neighbours do not
connect components.

The output must be a single JSON value – an integer – written to stdout.

The constraints are modest (max 300×300), so a simple breadth‑first search
or depth‑first search is sufficient.  Recursion depth would be too high for
the worst case, so an explicit stack is used.
"""

import sys
import json


def count_islands(grid):
    """Return the number of 4‑connected components of ``"1"`` in *grid*.

    Parameters
    ----------
    grid : list[str]
        List of binary strings.
    """
    if not grid:
        return 0
    rows = len(grid)
    cols = len(grid[0])
    visited = [[False] * cols for _ in range(rows)]
    islands = 0
    # Directions: up, down, left, right
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != '1' or visited[r][c]:
                continue
            islands += 1
            # BFS/DFS stack
            stack = [(r, c)]
            visited[r][c] = True
            while stack:
                cr, cc = stack.pop()
                for dr, dc in dirs:
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < rows and 0 <= nc < cols:
                        if not visited[nr][nc] and grid[nr][nc] == '1':
                            visited[nr][nc] = True
                            stack.append((nr, nc))
    return islands


def solve():
    data = json.load(sys.stdin)
    grid = data.get("grid", [])
    result = count_islands(grid)
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    solve()
