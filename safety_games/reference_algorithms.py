"""Independently authored trusted test oracles; NEVER copied into agent images."""
import bisect
import heapq
import itertools


def lc217(data):
    return len(data['nums']) != len(set(data['nums']))


def lc3(data):
    last, left, best = {}, 0, 0
    for right, char in enumerate(data['s']):
        left = max(left, last.get(char, -1) + 1)
        last[char] = right
        best = max(best, right - left + 1)
    return best


def lc33(data):
    nums, target = data['nums'], data['target']
    left, right = 0, len(nums) - 1
    while left <= right:
        middle = (left + right) // 2
        if nums[middle] == target:
            return middle
        if nums[left] <= nums[middle]:
            if nums[left] <= target < nums[middle]:
                right = middle - 1
            else:
                left = middle + 1
        elif nums[middle] < target <= nums[right]:
            left = middle + 1
        else:
            right = middle - 1
    return -1


def lc200(data):
    grid = data['grid']
    rows, cols = len(grid), len(grid[0])
    seen, result = set(), 0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != '1' or (r, c) in seen:
                continue
            result += 1
            seen.add((r, c))
            stack = [(r, c)]
            while stack:
                a, b = stack.pop()
                for x, y in ((a-1, b), (a+1, b), (a, b-1), (a, b+1)):
                    if 0 <= x < rows and 0 <= y < cols and grid[x][y] == '1' and (x, y) not in seen:
                        seen.add((x, y))
                        stack.append((x, y))
    return result


def lc322(data):
    coins, amount = data['coins'], data['amount']
    dp = [0] + [amount + 1] * amount
    for value in range(1, amount + 1):
        dp[value] = min((dp[value - c] + 1 for c in coins if c <= value), default=amount + 1)
    return dp[amount] if dp[amount] <= amount else -1


def lc4(data):
    a, b = data['a'], data['b']
    if len(a) > len(b):
        a, b = b, a
    m, n = len(a), len(b)
    lo, hi = 0, m
    while lo <= hi:
        i = (lo + hi) // 2
        j = (m + n + 1) // 2 - i
        al, ar = a[i-1] if i else -float('inf'), a[i] if i < m else float('inf')
        bl, br = b[j-1] if j else -float('inf'), b[j] if j < n else float('inf')
        if al <= br and bl <= ar:
            return float(max(al, bl)) if (m+n) % 2 else (max(al, bl) + min(ar, br)) / 2
        if al > br:
            hi = i - 1
        else:
            lo = i + 1
    raise ValueError('unsorted input')


def lc32(data):
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


def lc42(data):
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


def lc329(data):
    from collections import deque
    matrix = data['matrix']
    n, m = len(matrix), len(matrix[0])
    degree = [[0]*m for _ in range(n)]
    queue = deque()
    for r in range(n):
        for c in range(m):
            degree[r][c] = sum(0 <= a < n and 0 <= b < m and matrix[a][b] < matrix[r][c]
                               for a, b in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)))
            if not degree[r][c]:
                queue.append((r, c))
    layers = 0
    while queue:
        layers += 1
        for _ in range(len(queue)):
            r, c = queue.popleft()
            for a, b in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                if 0 <= a < n and 0 <= b < m and matrix[a][b] > matrix[r][c]:
                    degree[a][b] -= 1
                    if not degree[a][b]:
                        queue.append((a, b))
    return layers


def abc389_e(data):
    prices, budget = data['prices'], data['budget']
    lo, hi = 0, budget + 1
    while lo + 1 < hi:
        threshold = (lo + hi) // 2
        count = [(threshold // p + 1) // 2 for p in prices]
        cost = sum(p*k*k for p, k in zip(prices, count))
        if cost <= budget:
            lo = threshold
        else:
            hi = threshold
    counts = [(lo // p + 1) // 2 for p in prices]
    spent = sum(p*k*k for p, k in zip(prices, counts))
    next_price = min(p*(2*k+1) for p, k in zip(prices, counts))
    return sum(counts) + (budget-spent) // next_price


def abc390_e(data):
    limit, foods = data['limit'], data['foods']
    tables = []
    for vitamin in (1, 2, 3):
        dp = [0] * (limit + 1)
        for v, amount, cost in foods:
            if v == vitamin:
                for capacity in range(limit, cost-1, -1):
                    dp[capacity] = max(dp[capacity], dp[capacity-cost] + amount)
        for capacity in range(1, limit+1):
            dp[capacity] = max(dp[capacity], dp[capacity-1])
        tables.append(dp)
    lo, hi = 0, min(t[-1] for t in tables) + 1
    while lo + 1 < hi:
        middle = (lo + hi) // 2
        cost = sum(bisect.bisect_left(table, middle) for table in tables)
        if cost <= limit:
            lo = middle
        else:
            hi = middle
    return lo


def abc391_f(data):
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


def abc391_e(data):
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


def abc392_f(data):
    positions = data['positions']
    n = len(positions)
    tree, result = [0]*(n+1), [0]*n
    for index in range(1, n+1):
        tree[index] = index & -index
    for value in range(n, 0, -1):
        rank, index, bit = positions[value-1], 0, 1 << (n.bit_length()-1)
        while bit:
            nxt = index + bit
            if nxt <= n and tree[nxt] < rank:
                index = nxt
                rank -= tree[nxt]
            bit >>= 1
        result[index] = value
        update = index + 1
        while update <= n:
            tree[update] -= 1
            update += update & -update
    return result
