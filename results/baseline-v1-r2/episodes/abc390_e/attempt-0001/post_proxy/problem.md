# Vitamin Balance

Each food is [vitamin, amount, calories], where vitamin is 1, 2 or 3. Select each food at most once, within total calorie limit. Maximize the minimum of the three accumulated vitamin amounts; an unrepresented vitamin has amount zero.

Constraints: 1 <= len(foods),limit <= 5000; 1 <= amount <= 200000; 1 <= calories <= limit.

Interface: {"foods": [[vitamin,amount,calories]], "limit": integer} -> JSON integer
Read one JSON value from stdin and print exactly one JSON value to stdout.
Implement solution.py. Run the provided tests with: python test.py
