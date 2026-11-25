import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    stack, best = [-1], 0
    for i, char in enumerate(data['s']):
        if char == '(':
            stack.append(i)
        else:
            stack.pop()
            if stack:
                best = max(best, i - stack[-1])
            else:
                stack.append(i)
    return best


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
