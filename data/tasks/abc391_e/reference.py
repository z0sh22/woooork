import bisect
import heapq
import itertools
import json
import sys

def solve(data):
    nodes = [(0,1) if bit == '0' else (1,0) for bit in data['bits']]
    while len(nodes) > 1:
        next_nodes = []
        for i in range(0, len(nodes), 3):
            children = nodes[i:i+3]
            costs = []
            for target in (0, 1):
                costs.append(min(sum(child[value] for child, value in zip(children, values))
                                 for values in itertools.product((0,1), repeat=3) if sum(values) // 2 == target))
            next_nodes.append(tuple(costs))
        nodes = next_nodes
    return max(nodes[0])


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
