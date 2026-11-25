# Hierarchical Majority Vote

bits is a binary string of length 3^n for an integer n >= 1. Repeatedly replace each consecutive group of three bits by its majority bit until one bit remains. Return the minimum number of original bits that must be flipped to make that final bit change.

Constraints: 1 <= n <= 13; len(bits)=3^n; bits contains only 0 and 1.

Interface: {"bits": binary string} -> JSON integer
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
