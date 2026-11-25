import json
import sys


def solve(data):
    nums = data["nums"]
    target = data["target"]
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        # Determine which side is sorted
        if nums[lo] <= nums[mid]:  # left side sorted
            if nums[lo] <= target < nums[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        else:  # right side sorted
            if nums[mid] < target <= nums[hi]:
                lo = mid + 1
            else:
                hi = mid - 1
    return -1


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
