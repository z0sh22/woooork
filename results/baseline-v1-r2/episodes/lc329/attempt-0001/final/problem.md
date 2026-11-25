# Longest Increasing Path in a Matrix

From any matrix cell you may move to a side-adjacent cell with a strictly larger value. Return the maximum possible number of cells on a path. Diagonals and wrapping are not allowed.

Constraints: 1 <= rows,columns <= 200; integer cell values in [0,2^31-1].

Interface: {"matrix": [[integers]]} -> JSON integer
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
