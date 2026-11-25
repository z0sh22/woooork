import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    coins, amount = data['coins'], data['amount']
    dp = [0] + [amount + 1] * amount
    for value in range(1, amount + 1):
        dp[value] = min((dp[value - c] + 1 for c in coins if c <= value), default=amount + 1)
    return dp[amount] if dp[amount] <= amount else -1


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
