# Median of Two Sorted Arrays

Arrays data["a"] and data["b"] are individually sorted. Return the median of their combined multiset: its middle value for odd length, or the mean of the two middle values for even length. Aim for logarithmic complexity in total length.

Constraints: 0 <= len(a),len(b) <= 1000; total length >= 1; values in [-10^6,10^6].

Interface: {"a": [integers], "b": [integers]} -> JSON number (absolute error <= 1e-9)
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
