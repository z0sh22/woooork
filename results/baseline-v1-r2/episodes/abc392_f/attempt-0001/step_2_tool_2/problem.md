# Insert

Start with an empty array. For i=1..N, insert the integer i so that it occupies the one-based position positions[i-1], shifting the suffix right. Return the final array. Your method should scale to large N.

Constraints: 1 <= N <= 500000; 1 <= positions[i-1] <= i.

Interface: {"positions": [integers]} -> JSON array of integers
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
