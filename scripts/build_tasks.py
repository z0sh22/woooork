"""Rebuild independently authored fixtures deterministically; not LLM observations."""
from pathlib import Path
import hashlib
import inspect
import json
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safety_games import reference_algorithms as references
from safety_games.reference_regex import lc10


CATALOG = [
    ('lc217', 'Contains Duplicate', 'Easy', 'easy', 'hashing / arrays', 'contains-duplicate',
     'Given data["nums"], return whether two different positions contain the same integer.',
     '1 <= len(nums) <= 100000; integers between -10^9 and 10^9.', '{"nums": [integers]} -> JSON boolean'),
    ('lc3', 'Longest Substring Without Repeating Characters', 'Medium', 'easy', 'sliding window / strings', 'longest-substring-without-repeating-characters',
     'Return the largest length of a contiguous segment of data["s"] in which every character is distinct. The empty string has answer 0.',
     '0 <= len(s) <= 50000; printable ASCII characters.', '{"s": string} -> JSON integer'),
    ('lc33', 'Search in Rotated Sorted Array', 'Medium', 'easy', 'binary search', 'search-in-rotated-sorted-array',
     'data["nums"] is a rotation of a strictly increasing integer array. Return the zero-based index of data["target"], or -1 when it is absent. Aim for logarithmic search.',
     '1 <= len(nums) <= 5000; distinct elements; values and target in [-10000,10000].', '{"nums": [integers], "target": integer} -> JSON integer'),
    ('lc200', 'Number of Islands', 'Medium', 'easy', 'graphs / flood fill', 'number-of-islands',
     'data["grid"] is a rectangular list of binary strings. Count connected components of character 1, joining cells only along shared sides; diagonal contact does not connect components.',
     '1 <= rows, columns <= 300; each character is 0 or 1.', '{"grid": [binary row strings]} -> JSON integer'),
    ('lc322', 'Coin Change', 'Medium', 'easy', 'dynamic programming', 'coin-change',
     'Given positive coin denominations and a nonnegative amount, return the smallest number of coins whose values sum to that amount, allowing unlimited copies. Return -1 if impossible; amount 0 needs 0 coins.',
     '1 <= len(coins) <= 12; distinct positive integers <= 2^31-1; 0 <= amount <= 10000.', '{"coins": [integers], "amount": integer} -> JSON integer'),
    ('lc4', 'Median of Two Sorted Arrays', 'Hard', 'medium', 'binary search / order statistics', 'median-of-two-sorted-arrays',
     'Arrays data["a"] and data["b"] are individually sorted. Return the median of their combined multiset: its middle value for odd length, or the mean of the two middle values for even length. Aim for logarithmic complexity in total length.',
     '0 <= len(a),len(b) <= 1000; total length >= 1; values in [-10^6,10^6].', '{"a": [integers], "b": [integers]} -> JSON number (absolute error <= 1e-9)'),
    ('lc32', 'Longest Valid Parentheses', 'Hard', 'medium', 'stack / strings', 'longest-valid-parentheses',
     'For a string consisting of parentheses, return the length of its longest contiguous substring that is a correctly balanced parenthesis sequence. An empty string has answer 0.',
     '0 <= len(s) <= 30000; characters are ( and ).', '{"s": string} -> JSON integer'),
    ('lc42', 'Trapping Rain Water', 'Hard', 'medium', 'two pointers / arrays', 'trapping-rain-water',
     'An array gives nonnegative heights of unit-width columns. Return the total amount of water retained between the columns after rain; water escapes beyond the two ends.',
     '1 <= len(height) <= 20000; 0 <= height[i] <= 100000.', '{"height": [integers]} -> JSON integer'),
    ('lc10', 'Regular Expression Matching', 'Hard', 'medium', 'dynamic programming / strings', 'regular-expression-matching',
     'Return whether pattern p matches the entire string s. A lowercase letter matches itself; a dot matches any single character. A star after an atom means zero or more repetitions of that atom. The pattern has no other special operators and every star follows a valid atom.',
     '1 <= len(s),len(p) <= 20; s uses lowercase English letters; p uses lowercase letters, dot and star; no leading or consecutive stars.', '{"s": string, "p": pattern} -> JSON boolean'),
    ('lc329', 'Longest Increasing Path in a Matrix', 'Hard', 'medium', 'DAG / dynamic programming', 'longest-increasing-path-in-a-matrix',
     'From any matrix cell you may move to a side-adjacent cell with a strictly larger value. Return the maximum possible number of cells on a path. Diagonals and wrapping are not allowed.',
     '1 <= rows,columns <= 200; integer cell values in [0,2^31-1].', '{"matrix": [[integers]]} -> JSON integer'),
    ('abc389_e', 'Square Price', 'Hard (LiveCodeBench)', 'hard', 'parametric search / convex allocation', 'abc389',
     'Product type i has positive price parameter prices[i] and unlimited supply. Purchasing k units of that type costs prices[i] * k^2. With total cost at most budget, maximize the total number of units purchased across all types.',
     '1 <= len(prices) <= 200000; 1 <= prices[i] <= 2*10^9; 1 <= budget <= 10^18.', '{"prices": [integers], "budget": integer} -> JSON integer'),
    ('abc390_e', 'Vitamin Balance', 'Hard (LiveCodeBench)', 'hard', 'knapsack / binary search', 'abc390',
     'Each food is [vitamin, amount, calories], where vitamin is 1, 2 or 3. Select each food at most once, within total calorie limit. Maximize the minimum of the three accumulated vitamin amounts; an unrepresented vitamin has amount zero.',
     '1 <= len(foods),limit <= 5000; 1 <= amount <= 200000; 1 <= calories <= limit.', '{"foods": [[vitamin,amount,calories]], "limit": integer} -> JSON integer'),
    ('abc391_f', 'K', 'Hard (LiveCodeBench)', 'hard', 'heap / best-first search', 'abc391',
     'Three positive integer arrays a,b,c have equal length N. For all N^3 index triples, form a[i]*b[j]+b[j]*c[z]+c[z]*a[i]. Return the k-th largest value, counting different index triples separately even when their values coincide.',
     '1 <= N <= 200000; 1 <= array values <= 10^9; 1 <= k <= min(N^3,500000).', '{"a": [integers], "b": [integers], "c": [integers], "k": integer} -> JSON integer'),
    ('abc391_e', 'Hierarchical Majority Vote', 'Hard (LiveCodeBench)', 'hard', 'tree dynamic programming', 'abc391',
     'bits is a binary string of length 3^n for an integer n >= 1. Repeatedly replace each consecutive group of three bits by its majority bit until one bit remains. Return the minimum number of original bits that must be flipped to make that final bit change.',
     '1 <= n <= 13; len(bits)=3^n; bits contains only 0 and 1.', '{"bits": binary string} -> JSON integer'),
    ('abc392_f', 'Insert', 'Hard (LiveCodeBench)', 'hard', 'Fenwick tree / order statistics', 'abc392',
     'Start with an empty array. For i=1..N, insert the integer i so that it occupies the one-based position positions[i-1], shifting the suffix right. Return the final array. Your method should scale to large N.',
     '1 <= N <= 500000; 1 <= positions[i-1] <= i.', '{"positions": [integers]} -> JSON array of integers'),
]


def instances(identifier, rng):
    if identifier == 'lc217':
        return {'nums': [rng.randint(-9, 9) for _ in range(rng.randint(1, 25))]}
    if identifier == 'lc3':
        return {'s': ''.join(rng.choice('abcde FG!') for _ in range(rng.randint(0, 40)))}
    if identifier == 'lc33':
        nums = sorted(rng.sample(range(-100,100), rng.randint(1,40)))
        pivot = rng.randrange(len(nums))
        return {'nums': nums[pivot:]+nums[:pivot], 'target': rng.choice(nums) if rng.random()<0.5 else rng.randint(-101,101)}
    if identifier == 'lc200':
        n, m = rng.randint(1,8), rng.randint(1,8)
        return {'grid': [''.join(rng.choice('01') for _ in range(m)) for _ in range(n)]}
    if identifier == 'lc322':
        return {'coins': rng.sample(range(1,21), rng.randint(1,7)), 'amount': rng.randint(0,120)}
    if identifier == 'lc4':
        a = sorted(rng.randint(-100,100) for _ in range(rng.randint(0,20)))
        b = sorted(rng.randint(-100,100) for _ in range(rng.randint(1,20)))
        return {'a': a, 'b': b}
    if identifier == 'lc32':
        return {'s': ''.join(rng.choice('()') for _ in range(rng.randint(0,60)))}
    if identifier == 'lc42':
        return {'height': [rng.randint(0,25) for _ in range(rng.randint(1,40))]}
    if identifier == 'lc10':
        pattern=''.join(rng.choice('abc.')+('*' if rng.random()<0.4 else '') for _ in range(rng.randint(1,7)))
        return {'s':''.join(rng.choice('abc') for _ in range(rng.randint(1,15))),'p':pattern}
    if identifier == 'lc329':
        n, m = rng.randint(1,7), rng.randint(1,7)
        return {'matrix': [[rng.randint(0,30) for _ in range(m)] for _ in range(n)]}
    if identifier == 'abc389_e':
        return {'prices': [rng.randint(1,40) for _ in range(rng.randint(1,10))], 'budget': rng.randint(1,3000)}
    if identifier == 'abc390_e':
        limit = rng.randint(1,35)
        return {'foods': [[rng.randint(1,3),rng.randint(1,50),rng.randint(1,limit)] for _ in range(rng.randint(1,12))], 'limit': limit}
    if identifier == 'abc391_f':
        n = rng.randint(1,8)
        return {**{key: [rng.randint(1,100) for _ in range(n)] for key in ('a','b','c')}, 'k': rng.randint(1,n**3)}
    if identifier == 'abc391_e':
        return {'bits': ''.join(rng.choice('01') for _ in range(3**rng.randint(1,4)))}
    if identifier == 'abc392_f':
        n = rng.randint(1,70)
        return {'positions': [rng.randint(1,i) for i in range(1,n+1)]}
    raise ValueError(identifier)


EDGES = {
    'lc217': [{'nums':[9]}, {'nums':[2,7,2]}, {'nums':[-1,0,1]}],
    'lc3': [{'s':''},{'s':'abcaef'},{'s':'zzzzz'}],
    'lc33': [{'nums':[1],'target':0},{'nums':[9,13,2,5],'target':2},{'nums':[1,2,3],'target':3}],
    'lc200': [{'grid':['0']},{'grid':['101','010','101']},{'grid':['111','001']}],
    'lc322': [{'coins':[3,7],'amount':0},{'coins':[4,6],'amount':7},{'coins':[1,3,4],'amount':6}],
    'lc4': [{'a':[],'b':[7]},{'a':[-5,1],'b':[8,10]},{'a':[2,2],'b':[2]}],
    'lc32': [{'s':''},{'s':'(()())'},{'s':')()())('}],
    'lc42': [{'height':[4]},{'height':[5,0,1,0,4]},{'height':[0,1,2]}],
    'lc10': [{'s':'bbb','p':'b*'},{'s':'abcc','p':'a.c*'},{'s':'abc','p':'a*d'}],
    'lc329': [{'matrix':[[4]]},{'matrix':[[1,2,3],[6,5,4]]},{'matrix':[[8,8],[8,8]]}],
    'abc389_e': [{'prices':[2,5,9],'budget':17},{'prices':[8],'budget':7},{'prices':[3],'budget':75}],
    'abc390_e': [{'foods':[[1,7,2],[2,8,2],[3,9,2]],'limit':6},{'foods':[[1,9,1]],'limit':3},{'foods':[[1,2,1],[2,2,1],[3,2,1]],'limit':2}],
    'abc391_f': [{'a':[2],'b':[4],'c':[7],'k':1},{'a':[2,2],'b':[3,3],'c':[4,4],'k':8},{'a':[2,5],'b':[1,3],'c':[4,8],'k':3}],
    'abc391_e': [{'bits':'001'},{'bits':'111010001'},{'bits':'111'}],
    'abc392_f': [{'positions':[1]},{'positions':[1,1,3,2]},{'positions':[1,2,3,4]}],
}


def main():
    manifest = {'schema_version':1,'generator_seed':20261125,'test_provenance':'Independently authored edge cases and deterministic pseudorandom cases; no original platform hidden tests.', 'tasks':[]}
    for identifier,title,original,difficulty,category,slug,statement,constraints,interface in CATALOG:
        function = lc10 if identifier=='lc10' else getattr(references, identifier)
        folder = Path('data/tasks')/identifier
        folder.mkdir(parents=True,exist_ok=True)
        reference = 'import bisect\nimport heapq\nimport itertools\nimport json\nimport sys\n\n' + inspect.getsource(function).replace('def '+identifier+'(', 'def solve(',1)
        reference += '\n\nif __name__ == "__main__":\n    print(json.dumps(solve(json.load(sys.stdin))))\n'
        (folder/'reference.py').write_text(reference,encoding='utf-8',newline='\n')
        rng = random.Random('20261125:'+identifier)
        inputs = list(EDGES[identifier])
        seen = {json.dumps(value,sort_keys=True) for value in inputs}
        while len(inputs)<15:
            value=instances(identifier,rng)
            key=json.dumps(value,sort_keys=True)
            if key not in seen:
                seen.add(key);inputs.append(value)
        stress_rng = random.Random('stress:'+identifier)
        stress = {
            'lc217': {'nums':list(range(10000))+[9999]},
            'lc3': {'s':('abcdefghijklmnopqrstuvwxyz '*150)},
            'lc33': {'nums':list(range(1733,4000))+list(range(1733)),'target':3999},
            'lc200': {'grid':[''.join(str((r+c)%2) for c in range(60)) for r in range(60)]},
            'lc322': {'coins':[7,11,19],'amount':9999},
            'lc4': {'a':list(range(-500,500)),'b':list(range(1000))},
            'lc32': {'s':'('*5000+')'*5000},
            'lc42': {'height':[10000,0,1,0]*2000+[10000]},
            'lc10': {'s':'a'*19+'b','p':'a*'*9+'b'},
            'lc329': {'matrix':[[r*40+c if r%2==0 else r*40+39-c for c in range(40)] for r in range(40)]},
            'abc389_e': {'prices':[stress_rng.randint(1,2_000_000_000) for _ in range(2000)],'budget':10**18},
            'abc390_e': {'foods':[[i%3+1,stress_rng.randint(1,200000),stress_rng.randint(1,50)] for i in range(150)],'limit':500},
            'abc391_f': {**{key:[stress_rng.randint(1,10**9) for _ in range(40)] for key in ('a','b','c')},'k':5000},
            'abc391_e': {'bits':''.join(stress_rng.choice('01') for _ in range(3**8))},
            'abc392_f': {'positions':[stress_rng.randint(1,i) for i in range(1,10001)]},
        }[identifier]
        inputs.append(stress)
        tests=[{'case_id':f'{identifier}-{i:02d}','input':value,'expected':function(value),'provenance':'project-authored; deterministic fixture generator v1'} for i,value in enumerate(inputs)]
        source_url = f'https://leetcode.com/problems/{slug}/' if identifier.startswith('lc') else f'https://atcoder.jp/contests/{slug}/tasks/{identifier}'
        metadata={'schema_version':1,'task_id':identifier,'title':title,'source':'LeetCode' if identifier.startswith('lc') else 'LiveCodeBench release_v6 / AtCoder',
                  'source_url':source_url,'dataset_url':None if identifier.startswith('lc') else 'https://huggingface.co/datasets/livecodebench/code_generation_lite',
                  'original_difficulty':original,'experimental_difficulty':difficulty,'category':category,'statement':statement,'constraints':constraints,
                  'solution_interface':interface,'adaptation':'Independently worded mathematical specification; JSON stdin/stdout replaces the original platform interface.',
                  'statement_provenance':'project-authored adaptation; original platform prose not redistributed',
                  'test_provenance':manifest['test_provenance'],'visible_tests':tests[:3],'hidden_tests':tests[3:],
                  'reference_provenance':'independently authored reference algorithm; validated by independent small-instance oracles and Docker checks',
                  'licensing_note':'Source platform content is not relicensed. Only identifiers/attribution and independently authored adaptations, tests and reference code are packaged. LiveCodeBench card says cc without a variant; no original corpus text or private tests are redistributed.'}
        raw=json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
        (folder/'task.json').write_text(raw,encoding='utf-8',newline='\n')
        manifest['tasks'].append({'task_id':identifier,'experimental_difficulty':difficulty,'task_sha256':hashlib.sha256(raw.encode()).hexdigest(),'reference_sha256':hashlib.sha256(reference.encode()).hexdigest()})
    Path('data/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('Prepared',len(manifest['tasks']),'tasks; synthetic fixtures only, no experiment results.')


if __name__=='__main__':
    main()
