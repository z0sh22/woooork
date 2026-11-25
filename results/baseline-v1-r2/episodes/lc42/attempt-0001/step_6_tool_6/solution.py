import json
import sys


def solve(data):
    """Compute total trapped rain water for given heights.

    Parameters
    ----------
    data : dict
        Dictionary containing key "height" mapping to a list of non‑negative
        integers.

    Returns
    -------
    int
        Total units of water that can be trapped.
    """
    heights = data.get("height", [])
    n = len(heights)
    if n < 3:
        return 0
    left, right = 0, n - 1
    left_max, right_max = heights[left], heights[right]
    trapped = 0
    while left < right:
        if left_max <= right_max:
            left += 1
            left_max = max(left_max, heights[left])
            trapped += max(0, left_max - heights[left])
        else:
            right -= 1
            right_max = max(right_max, heights[right])
            trapped += max(0, right_max - heights[right])
    return trapped


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
