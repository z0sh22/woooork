# Regular Expression Matching

Return whether pattern p matches the entire string s. A lowercase letter matches itself; a dot matches any single character. A star after an atom means zero or more repetitions of that atom. The pattern has no other special operators and every star follows a valid atom.

Constraints: 1 <= len(s),len(p) <= 20; s uses lowercase English letters; p uses lowercase letters, dot and star; no leading or consecutive stars.

Interface: {"s": string, "p": pattern} -> JSON boolean
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
