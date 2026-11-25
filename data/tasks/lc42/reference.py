import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    height = data['height']
    left, right, lm, rm, total = 0, len(height)-1, 0, 0, 0
    while left <= right:
        if lm <= rm:
            lm = max(lm, height[left])
            total += lm - height[left]
            left += 1
        else:
            rm = max(rm, height[right])
            total += rm - height[right]
            right -= 1
    return total


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
