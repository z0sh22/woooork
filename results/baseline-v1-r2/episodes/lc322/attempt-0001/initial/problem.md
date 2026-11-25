# Coin Change

Given positive coin denominations and a nonnegative amount, return the smallest number of coins whose values sum to that amount, allowing unlimited copies. Return -1 if impossible; amount 0 needs 0 coins.

Constraints: 1 <= len(coins) <= 12; distinct positive integers <= 2^31-1; 0 <= amount <= 10000.

Interface: {"coins": [integers], "amount": integer} -> JSON integer
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
