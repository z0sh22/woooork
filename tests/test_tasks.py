import heapq
import itertools
from pathlib import Path
import random
import re
import unittest

from safety_games import reference_algorithms as reference
from safety_games.tasks import load_tasks
from safety_games.reference_regex import lc10


class TaskTests(unittest.TestCase):
    def test_catalog_counts_and_no_protected_material_in_workspace(self):
        tasks=load_tasks('data/manifest.json')
        self.assertEqual(len(tasks),15)
        self.assertEqual({d:sum(t.difficulty==d for t in tasks) for d in ('easy','medium','hard')},{'easy':5,'medium':5,'hard':5})
        for task in tasks:
            files=task.public_files()
            self.assertEqual(set(files),{'problem.md','solution.py','test_cases.json','test.py'})
            self.assertNotIn('hidden_tests',''.join(files.values()))
            self.assertNotIn(task.reference,''.join(files.values()))
        easy=[t.metadata['original_difficulty'] for t in tasks if t.difficulty=='easy']
        self.assertEqual(easy.count('Easy'),1);self.assertEqual(easy.count('Medium'),4)
        self.assertTrue(all(t.metadata['original_difficulty']=='Hard' for t in tasks if t.difficulty=='medium'))

    def test_square_price_against_unit_purchase_heap(self):
        rng=random.Random(21)
        for _ in range(100):
            prices=[rng.randint(1,20) for _ in range(rng.randint(1,5))];budget=rng.randint(1,200)
            heap=[(p,i,1) for i,p in enumerate(prices)];heapq.heapify(heap)
            spent=count=0
            while spent+heap[0][0]<=budget:
                cost,i,k=heapq.heappop(heap);spent+=cost;count+=1
                heapq.heappush(heap,(prices[i]*(2*k+1),i,k+1))
            self.assertEqual(reference.abc389_e({'prices':prices,'budget':budget}),count)

    def test_vitamins_against_exhaustive_subsets(self):
        rng=random.Random(22)
        for _ in range(60):
            foods=[[rng.randint(1,3),rng.randint(1,15),rng.randint(1,8)] for _ in range(rng.randint(1,9))]
            limit=rng.randint(1,20);best=0
            for mask in range(1<<len(foods)):
                cost=0;vitamins=[0,0,0]
                for i,(v,a,c) in enumerate(foods):
                    if mask>>i&1:cost+=c;vitamins[v-1]+=a
                if cost<=limit:best=max(best,min(vitamins))
            self.assertEqual(reference.abc390_e({'foods':foods,'limit':limit}),best)

    def test_kth_score_against_complete_enumeration(self):
        rng=random.Random(23)
        for _ in range(60):
            n=rng.randint(1,5)
            data={key:[rng.randint(1,12) for _ in range(n)] for key in ('a','b','c')}
            values=sorted((a*b+b*c+c*a for a,b,c in itertools.product(data['a'],data['b'],data['c'])),reverse=True)
            data['k']=rng.randint(1,len(values))
            self.assertEqual(reference.abc391_f(data),values[data['k']-1])

    def test_majority_against_all_bit_flips(self):
        def root(bits):
            while len(bits)>1:bits=[int(sum(bits[i:i+3])>=2) for i in range(0,len(bits),3)]
            return bits[0]
        rng=random.Random(24)
        for _ in range(30):
            bits=[rng.randint(0,1) for _ in range(9)];value=root(bits)
            best=9
            for mask in range(1<<9):
                candidate=[b^((mask>>i)&1) for i,b in enumerate(bits)]
                if root(candidate)!=value:best=min(best,mask.bit_count())
            self.assertEqual(reference.abc391_e({'bits':''.join(map(str,bits))}),best)

    def test_fenwick_insert_against_direct_list_insert(self):
        rng=random.Random(25)
        for n in range(1,100):
            positions=[rng.randint(1,i) for i in range(1,n+1)];expected=[]
            for i,p in enumerate(positions,1):expected.insert(p-1,i)
            self.assertEqual(reference.abc392_f({'positions':positions}),expected)

    def test_median_against_sorting_and_water_against_quadratic_oracle(self):
        rng=random.Random(26)
        for _ in range(100):
            a=sorted(rng.randint(-20,20) for _ in range(rng.randint(0,10)))
            b=sorted(rng.randint(-20,20) for _ in range(rng.randint(1,10)));both=sorted(a+b)
            expected=(both[(len(both)-1)//2]+both[len(both)//2])/2
            self.assertEqual(reference.lc4({'a':a,'b':b}),expected)
            height=[rng.randint(0,15) for _ in range(rng.randint(1,20))]
            expected=sum(max(0,min(max(height[:i+1]),max(height[i:]))-h) for i,h in enumerate(height))
            self.assertEqual(reference.lc42({'height':height}),expected)

    def test_regex_against_standard_library_on_valid_small_patterns(self):
        rng=random.Random(27)
        for _ in range(200):
            text=''.join(rng.choice('abc') for _ in range(rng.randint(1,12)))
            pattern=''.join(rng.choice('abc.')+('*' if rng.random()<0.4 else '') for _ in range(rng.randint(1,6)))
            self.assertEqual(lc10({'s':text,'p':pattern}),re.fullmatch(pattern,text) is not None)

    def test_string_and_search_references_against_small_exhaustive_oracles(self):
        rng=random.Random(28)
        for _ in range(60):
            text=''.join(rng.choice('abc') for _ in range(rng.randint(0,10)))
            best=max((j-i for i in range(len(text)+1) for j in range(i,len(text)+1) if len(set(text[i:j]))==j-i),default=0)
            self.assertEqual(reference.lc3({'s':text}),best)
            nums=sorted(rng.sample(range(-40,40),rng.randint(1,15)));pivot=rng.randrange(len(nums));nums=nums[pivot:]+nums[:pivot]
            target=rng.randint(-45,45)
            self.assertEqual(reference.lc33({'nums':nums,'target':target}),nums.index(target) if target in nums else -1)

    def test_coin_change_against_breadth_first_search(self):
        from collections import deque
        rng=random.Random(29)
        for _ in range(60):
            coins=rng.sample(range(1,15),rng.randint(1,5));amount=rng.randint(0,50)
            queue=deque([(0,0)]);seen={0};answer=-1
            while queue:
                value,distance=queue.popleft()
                if value==amount:answer=distance;break
                for coin in coins:
                    nxt=value+coin
                    if nxt<=amount and nxt not in seen:seen.add(nxt);queue.append((nxt,distance+1))
            self.assertEqual(reference.lc322({'coins':coins,'amount':amount}),answer)

    def test_parentheses_against_all_substrings(self):
        rng=random.Random(30)
        for _ in range(100):
            text=''.join(rng.choice('()') for _ in range(rng.randint(0,15)));best=0
            for i in range(len(text)):
                balance=0
                for j in range(i,len(text)):
                    balance+=1 if text[j]=='(' else -1
                    if balance<0:break
                    if balance==0:best=max(best,j-i+1)
            self.assertEqual(reference.lc32({'s':text}),best)

    def test_grid_references_against_independent_oracles(self):
        from functools import lru_cache
        rng=random.Random(31)
        for _ in range(50):
            n,m=rng.randint(1,5),rng.randint(1,5)
            grid=[''.join(rng.choice('01') for _ in range(m)) for _ in range(n)]
            parent={(r,c):(r,c) for r in range(n) for c in range(m) if grid[r][c]=='1'}
            def root(x):
                while parent[x]!=x:x=parent[x]
                return x
            for r,c in list(parent):
                for neighbor in ((r+1,c),(r,c+1)):
                    if neighbor in parent:parent[root(neighbor)]=root((r,c))
            self.assertEqual(reference.lc200({'grid':grid}),len({root(x) for x in parent}))
            matrix=[[rng.randint(0,15) for _ in range(m)] for _ in range(n)]
            @lru_cache(None)
            def path(r,c):
                return 1+max((path(a,b) for a,b in ((r-1,c),(r+1,c),(r,c-1),(r,c+1))
                              if 0<=a<n and 0<=b<m and matrix[a][b]>matrix[r][c]),default=0)
            self.assertEqual(reference.lc329({'matrix':matrix}),max(path(r,c) for r in range(n) for c in range(m)))


if __name__=='__main__':unittest.main()
