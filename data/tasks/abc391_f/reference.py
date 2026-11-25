import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    a, b, c = (sorted(data[key], reverse=True) for key in ('a', 'b', 'c'))
    n, k = len(a), data['k']
    def score(i, j, z):
        return a[i]*b[j] + b[j]*c[z] + c[z]*a[i]
    heap, seen = [(-score(0,0,0), 0,0,0)], {(0,0,0)}
    for _ in range(k):
        negative, i, j, z = heapq.heappop(heap)
        for index in ((i+1,j,z),(i,j+1,z),(i,j,z+1)):
            if max(index) < n and index not in seen:
                seen.add(index)
                heapq.heappush(heap, (-score(*index), *index))
    return -negative


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
