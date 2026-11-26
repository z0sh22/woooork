"""Static catalog checks and descriptive profiles; never run candidate code."""
import json
from pathlib import Path
import statistics

from .artifacts import write_json
from .logging import _atomic_write
from .preservation import ensure_not_frozen
from .tasks import load_tasks

COMPLEXITIES = {
    'lc217': ('O(n)', 'O(n)', 'n', 100000),
    'lc3': ('O(n)', 'O(alphabet)', 'n', 50000),
    'lc33': ('O(log n)', 'O(1)', 'n', 5000),
    'lc200': ('O(rows*columns)', 'O(rows*columns)', 'cells', 90000),
    'lc322': ('O(amount*len(coins))', 'O(amount)', 'amount', 10000),
    'lc4': ('O(log min(m,n))', 'O(1)', 'n+m', 2000),
    'lc32': ('O(n)', 'O(n)', 'n', 30000),
    'lc42': ('O(n)', 'O(1)', 'n', 20000),
    'lc10': ('O(len(s)*len(p))', 'O(len(s)*len(p))', 'len(s)*len(p)', 400),
    'lc329': ('O(rows*columns)', 'O(rows*columns)', 'cells', 40000),
    'abc389_e': ('O(n*log budget)', 'O(n)', 'n', 200000),
    'abc390_e': ('O(n*limit + limit*log(total_vitamins))', 'O(limit)', 'n*limit', 25000000),
    'abc391_f': ('O(n log n + k log k)', 'O(n+k)', 'k', 500000),
    'abc391_e': ('O(3^n)', 'O(3^n)', 'len(bits)', 1594323),
    'abc392_f': ('O(n log n)', 'O(n)', 'n', 500000),
}


def validate_input(task_id, d):
    def integer(x, low, high):
        return type(x) is int and low <= x <= high
    def seq(a, lo, hi, low, high):
        return isinstance(a, list) and lo <= len(a) <= hi and all(integer(x, low, high) for x in a)
    try:
        if task_id == 'lc217': return seq(d['nums'],1,100000,-10**9,10**9)
        if task_id == 'lc3': return isinstance(d['s'],str) and len(d['s'])<=50000 and all(32<=ord(c)<=126 for c in d['s'])
        if task_id == 'lc33':
            a=d['nums']; ordered=sorted(a)
            return seq(a,1,5000,-10000,10000) and len(set(a))==len(a) and integer(d['target'],-10000,10000) and any(a == ordered[i:]+ordered[:i] for i in range(len(a)))
        if task_id == 'lc200':
            a=d['grid'];return 1<=len(a)<=300 and 1<=len(a[0])<=300 and all(len(r)==len(a[0]) and set(r)<=set('01') for r in a)
        if task_id == 'lc322': return seq(d['coins'],1,12,1,2**31-1) and len(set(d['coins']))==len(d['coins']) and integer(d['amount'],0,10000)
        if task_id == 'lc4': return all(seq(d[k],0,1000,-10**6,10**6) and d[k]==sorted(d[k]) for k in ('a','b')) and len(d['a'])+len(d['b'])>=1
        if task_id == 'lc32': return isinstance(d['s'],str) and len(d['s'])<=30000 and set(d['s'])<=set('()')
        if task_id == 'lc42': return seq(d['height'],1,20000,0,100000)
        if task_id == 'lc10':
            s,p=d['s'],d['p']
            return 1<=len(s)<=20 and 1<=len(p)<=20 and set(s)<=set('abcdefghijklmnopqrstuvwxyz') and set(p)<=set('abcdefghijklmnopqrstuvwxyz.*') and not p.startswith('*') and '**' not in p
        if task_id == 'lc329':
            a=d['matrix'];return 1<=len(a)<=200 and 1<=len(a[0])<=200 and all(seq(row,len(a[0]),len(a[0]),0,2**31-1) for row in a)
        if task_id == 'abc389_e': return seq(d['prices'],1,200000,1,2*10**9) and integer(d['budget'],1,10**18)
        if task_id == 'abc390_e':
            return integer(d['limit'],1,5000) and 1<=len(d['foods'])<=5000 and all(len(f)==3 and integer(f[0],1,3) and integer(f[1],1,200000) and integer(f[2],1,d['limit']) for f in d['foods'])
        if task_id == 'abc391_f':
            n=len(d['a']);return all(seq(d[k],n,n,1,10**9) for k in ('a','b','c')) and 1<=n<=200000 and integer(d['k'],1,min(n**3,500000))
        if task_id == 'abc391_e': return set(d['bits'])<=set('01') and len(d['bits']) in (3**n for n in range(1,14))
        if task_id == 'abc392_f': return 1<=len(d['positions'])<=500000 and all(integer(p,1,i) for i,p in enumerate(d['positions'],1))
    except (KeyError, TypeError, IndexError):
        return False
    raise ValueError('No constraint validator for task: '+task_id)


def _scale(task_id, d):
    if task_id in ('lc217','lc33'):return len(d['nums'])
    if task_id in ('lc3','lc32'):return len(d['s'])
    if task_id == 'lc200':return len(d['grid'])*len(d['grid'][0])
    if task_id == 'lc322':return d['amount']
    if task_id == 'lc4':return len(d['a'])+len(d['b'])
    if task_id == 'lc42':return len(d['height'])
    if task_id == 'lc10':return len(d['s'])*len(d['p'])
    if task_id == 'lc329':return len(d['matrix'])*len(d['matrix'][0])
    if task_id == 'abc389_e':return len(d['prices'])
    if task_id == 'abc390_e':return len(d['foods'])*d['limit']
    if task_id == 'abc391_f':return d['k']
    if task_id == 'abc391_e':return len(d['bits'])
    return len(d['positions'])


def profile_tasks(manifest, output):
    output=Path(output);ensure_not_frozen(output);output.mkdir(parents=True,exist_ok=True)
    tasks=load_tasks(manifest)
    rows=[]
    for task in tasks:
        meta=task.metadata
        cases=meta['visible_tests']+meta['hidden_tests']
        complexity, memory, scale, maximum=COMPLEXITIES[task.task_id]
        invalid=[c['case_id'] for c in cases if not validate_input(task.task_id,c['input'])]
        rows.append({'task_id':task.task_id,'difficulty':task.difficulty,'source':meta['source'],
                     'category':meta['category'],'statement_chars':len(meta['statement']),
                     'problem_chars':len(task.public_files()['problem.md']),
                     'interface_chars':len(meta['solution_interface']),
                     'max_fixture_input_bytes':max(len(json.dumps(c['input']).encode()) for c in cases),
                     'reference_time_complexity':complexity,'reference_space_complexity':memory,
                     'scale_variable':scale,'declared_max_scale':maximum,
                     'largest_fixture_scale':max(_scale(task.task_id,c['input']) for c in cases),
                     'constraint_violations':invalid,
                     'worst_case_single_input_exceeds_sandbox_bytes': task.task_id in ('lc217','lc329','abc389_e','abc391_f','abc391_e','abc392_f')})
    write_json(output/'task_profiles.json',{'tasks':rows,'all_fixture_constraints_valid':not any(r['constraint_violations'] for r in rows),
               'note':'Complexities are manual analysis of trusted references, not empirical model difficulty. Source/level are confounded. Max-scale fixture coverage is not correctness coverage.'})
    lines=['# Описательный анализ исходных задач', '',
           '| task_id | Уровень | Категория | Условие, символы | Интерфейс, символы | max fixture scale / declared max | Проверка ограничений |',
           '| --- | --- | --- | ---: | ---: | --- | --- |']
    for r in rows:
        lines.append(f"| {r['task_id']} | {r['difficulty']} | {r['category']} | {r['statement_chars']} | {r['interface_chars']} | {r['largest_fixture_scale']}/{r['declared_max_scale']} ({r['scale_variable']}) | {r['constraint_violations'] or 'OK'} |")
    lines += ['', 'Таблица описывает исходные данные без их изменения. Полные worst-case входы нескольких олимпиадных задач '
              'превышают лимит передачи 262144 байта; конечный набор fixtures существенно меньше исходных ограничений. '
              'True Success нельзя интерпретировать как проверку полной асимптотики.', '',
              '## Длина условий по уровням', '']
    for d in ('easy','medium','hard'):
        values=[r['problem_chars'] for r in rows if r['difficulty']==d]
        lines.append(f'- {d}: полное problem.md, min={min(values)}, median={statistics.median(values)}, max={max(values)} символов.')
    _atomic_write(output/'task_profiles.md','\n'.join(lines)+'\n')
    return rows
