"""Trusted independent reference for LeetCode 10's adapted JSON interface."""


def lc10(data):
    text, pattern = data['s'], data['p']
    n, m = len(text), len(pattern)
    dp = [[False]*(m+1) for _ in range(n+1)]
    dp[0][0] = True
    for j in range(2,m+1):
        if pattern[j-1]=='*':
            dp[0][j]=dp[0][j-2]
    for i in range(1,n+1):
        for j in range(1,m+1):
            if pattern[j-1]=='*':
                dp[i][j]=dp[i][j-2] or (pattern[j-2] in ('.',text[i-1]) and dp[i-1][j])
            elif pattern[j-1] in ('.',text[i-1]):
                dp[i][j]=dp[i-1][j-1]
    return dp[n][m]
