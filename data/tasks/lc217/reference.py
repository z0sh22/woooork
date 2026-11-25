import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    return len(data['nums']) != len(set(data['nums']))


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
