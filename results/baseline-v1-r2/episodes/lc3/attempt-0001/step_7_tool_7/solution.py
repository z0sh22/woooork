import json
import sys


def solve(data):
    """Return the length of the longest substring without repeating characters.

    Parameters
    ----------
    data : dict
        Dictionary containing the key "s" with the input string.

    Returns
    -------
    int
        Length of the longest contiguous substring with all distinct characters.
    """
    s = data.get("s", "")
    last_seen = {}
    max_len = 0
    start = 0
    for i, ch in enumerate(s):
        if ch in last_seen and last_seen[ch] >= start:
            start = last_seen[ch] + 1
        last_seen[ch] = i
        curr_len = i - start + 1
        if curr_len > max_len:
            max_len = curr_len
    return max_len


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
