import json
import sys


def solve(data):
    """Return length of longest valid parentheses substring.

    Parameters
    ----------
    data : dict
        Expected to contain a key ``"s"`` with a string of ``(" or ")``.

    Returns
    -------
    int
        Length of the longest contiguous substring that is a correctly
        balanced parenthesis sequence.
    """
    s = data.get("s", "")
    n = len(s)
    if n == 0:
        return 0
    max_len = 0
    stack = [-1]  # stack of indices of '(' or sentinel
    for i, ch in enumerate(s):
        if ch == '(':
            stack.append(i)
        else:  # ch == ')'
            if stack:
                stack.pop()
            if not stack:
                stack.append(i)
            else:
                max_len = max(max_len, i - stack[-1])
    return max_len


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
