# K

Three positive integer arrays a,b,c have equal length N. For all N^3 index triples, form a[i]*b[j]+b[j]*c[z]+c[z]*a[i]. Return the k-th largest value, counting different index triples separately even when their values coincide.

Constraints: 1 <= N <= 200000; 1 <= array values <= 10^9; 1 <= k <= min(N^3,500000).

Interface: {"a": [integers], "b": [integers], "c": [integers], "k": integer} -> JSON integer
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
