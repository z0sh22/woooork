# Number of Islands

data["grid"] is a rectangular list of binary strings. Count connected components of character 1, joining cells only along shared sides; diagonal contact does not connect components.

Constraints: 1 <= rows, columns <= 300; each character is 0 or 1.

Interface: {"grid": [binary row strings]} -> JSON integer
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
