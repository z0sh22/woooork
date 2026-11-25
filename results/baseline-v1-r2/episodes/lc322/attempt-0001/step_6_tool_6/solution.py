import json
import sys


def solve(data):
    # Extract coins and amount
    coins = data.get("coins", [])
    amount = data.get("amount", 0)
    # Edge case: amount 0
    if amount == 0:
        return 0
    # Initialize DP array
    INF = amount + 1  # any value > amount is effectively infinite
    dp = [INF] * (amount + 1)
    dp[0] = 0
    # Iterate over coins
    for coin in coins:
        if coin <= 0:
            # Skip non-positive denominations (though problem says positive)
            continue
        for a in range(coin, amount + 1):
            if dp[a - coin] + 1 < dp[a]:
                dp[a] = dp[a - coin] + 1
    return dp[amount] if dp[amount] <= amount else -1


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
