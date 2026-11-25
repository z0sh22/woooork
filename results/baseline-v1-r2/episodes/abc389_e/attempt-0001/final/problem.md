# Square Price

Product type i has positive price parameter prices[i] and unlimited supply. Purchasing k units of that type costs prices[i] * k^2. With total cost at most budget, maximize the total number of units purchased across all types.

Constraints: 1 <= len(prices) <= 200000; 1 <= prices[i] <= 2*10^9; 1 <= budget <= 10^18.

Interface: {"prices": [integers], "budget": integer} -> JSON integer
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
