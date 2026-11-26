# Описательный анализ исходных задач

| task_id | Уровень | Категория | Условие, символы | Интерфейс, символы | max fixture scale / declared max | Проверка ограничений |
| --- | --- | --- | ---: | ---: | --- | --- |
| lc217 | easy | hashing / arrays | 84 | 36 | 10001/100000 (n) | OK |
| lc3 | easy | sliding window / strings | 131 | 29 | 4050/50000 (n) | OK |
| lc33 | easy | binary search | 166 | 55 | 4000/5000 (n) | OK |
| lc200 | easy | graphs / flood fill | 181 | 46 | 3600/90000 (cells) | OK |
| lc322 | easy | dynamic programming | 204 | 56 | 9999/10000 (amount) | OK |
| lc4 | medium | binary search / order statistics | 236 | 74 | 2000/2000 (n+m) | OK |
| lc32 | medium | stack / strings | 174 | 29 | 10000/30000 (n) | OK |
| lc42 | medium | two pointers / arrays | 166 | 38 | 8001/20000 (n) | OK |
| lc10 | medium | dynamic programming / strings | 270 | 43 | 380/400 (len(s)*len(p)) | OK |
| lc329 | medium | DAG / dynamic programming | 182 | 40 | 1600/40000 (cells) | OK |
| abc389_e | hard | parametric search / convex allocation | 225 | 57 | 2000/200000 (n) | OK |
| abc390_e | hard | knapsack / binary search | 233 | 72 | 75000/25000000 (n*limit) | OK |
| abc391_f | hard | heap / best-first search | 227 | 81 | 5000/500000 (k) | OK |
| abc391_e | hard | tree dynamic programming | 254 | 39 | 6561/1594323 (len(bits)) | OK |
| abc392_f | hard | Fenwick tree / order statistics | 206 | 51 | 10000/500000 (n) | OK |

Таблица описывает исходные данные без их изменения. Полные worst-case входы нескольких олимпиадных задач превышают лимит передачи 262144 байта; конечный набор fixtures существенно меньше исходных ограничений. True Success нельзя интерпретировать как проверку полной асимптотики.

## Длина условий по уровням

- easy: полное problem.md, min=371, median=471, max=528 символов.
- medium: полное problem.md, min=448, median=492, max=647 символов.
- hard: полное problem.md, min=481, median=550, max=572 символов.
