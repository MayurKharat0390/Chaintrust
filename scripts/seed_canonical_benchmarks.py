"""
scripts/seed_canonical_benchmarks.py
Enriches the database with genuine canonical HumanEval & MBPP benchmark tasks:
- Full problem prompts & docstrings with type annotations
- Canonical reference standard solutions
- Comprehensive hidden unit test suites
"""

from chaintrust.db.session import get_session
from chaintrust.db.models import Task, TaskSource

CANONICAL_TASKS = [
    {
        "task_id": "humaneval/HumanEval_0",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "has_close_elements",
        "prompt": '''from typing import List

def has_close_elements(numbers: List[float], threshold: float) -> bool:
    """ Check if in given list of numbers, are any two numbers closer to each other than
    given threshold.
    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)
    False
    >>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)
    True
    """
''',
        "reference_solution": '''    for idx, elem in enumerate(numbers):
        for idx2, elem2 in enumerate(numbers):
            if idx != idx2:
                distance = abs(elem - elem2)
                if distance < threshold:
                    return True
    return False
''',
        "tests": '''def check(candidate):
    assert candidate([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.3) == True
    assert candidate([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.05) == False
    assert candidate([1.0, 2.0, 5.9, 4.0, 5.0], 0.95) == True
    assert candidate([1.0, 2.0, 5.9, 4.0, 5.0], 0.8) == False
    assert candidate([1.0, 2.0, 3.0, 4.0, 5.0, 2.0], 0.1) == True
    assert candidate([1.1, 2.2, 3.1, 4.1, 5.1], 1.0) == True
    assert candidate([1.1, 2.2, 3.1, 4.1, 5.1], 0.5) == False
'''
    },
    {
        "task_id": "humaneval/HumanEval_1",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "separate_paren_groups",
        "prompt": '''from typing import List

def separate_paren_groups(paren_string: str) -> List[str]:
    """ Input to this function is a string containing multiple groups of nested parentheses. Your goal is to
    separate those group into separate strings and return the list of those.
    Separate groups are balanced (each open brace is properly closed) and not nested within each other
    Ignore any spaces in the input string.
    >>> separate_paren_groups('( ) (( )) (( )( ))')
    ['()', '(())', '(()())']
    """
''',
        "reference_solution": '''    result = []
    current_string = []
    current_depth = 0

    for c in paren_string:
        if c == '(':
            current_depth += 1
            current_string.append(c)
        elif c == ')':
            current_depth -= 1
            current_string.append(c)
            if current_depth == 0:
                result.append(''.join(current_string))
                current_string.clear()

    return result
''',
        "tests": '''def check(candidate):
    assert candidate('(()()) ((())) () ((())()())') == ['(()())', '((()))', '()', '((())()())']
    assert candidate('() (()) ((())) (((())))') == ['()', '(())', '((()))', '(((())))']
    assert candidate('(()(())((())))') == ['(()(())((())))']
    assert candidate('( ) (( )) (( )( ))') == ['()', '(())', '(()())']
'''
    },
    {
        "task_id": "humaneval/HumanEval_2",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "truncate_number",
        "prompt": '''def truncate_number(number: float) -> float:
    """ Given a positive floating point number, it can be decomposed into
    and integer part (largest integer smaller than given number) and decimals
    (leftover part always smaller than 1).

    Return the decimal part of the number.
    >>> truncate_number(3.5)
    0.5
    """
''',
        "reference_solution": '''    return number % 1.0
''',
        "tests": '''def check(candidate):
    assert abs(candidate(3.5) - 0.5) < 1e-6
    assert abs(candidate(1.33) - 0.33) < 1e-6
    assert abs(candidate(123.456) - 0.456) < 1e-6
'''
    },
    {
        "task_id": "humaneval/HumanEval_3",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "below_zero",
        "prompt": '''from typing import List

def below_zero(operations: List[int]) -> bool:
    """ You're given a list of deposit and withdrawal operations on a bank account that starts with
    zero balance. Your task is to detect if at any point the balance of account falls below zero, and
    at that point function should return True. Otherwise it should return False.
    >>> below_zero([1, 2, 3])
    False
    >>> below_zero([1, 2, -4, 5])
    True
    """
''',
        "reference_solution": '''    balance = 0
    for op in operations:
        balance += op
        if balance < 0:
            return True
    return False
''',
        "tests": '''def check(candidate):
    assert candidate([]) == False
    assert candidate([1, 2, -3, 1, 2, -3]) == False
    assert candidate([1, 2, -4, 5, 6]) == True
    assert candidate([1, -1, 2, -2, 5, -5, 4, -4]) == False
    assert candidate([1, -1, 2, -2, 5, -5, 4, -5]) == True
    assert candidate([1, -2, 2, -2, 5, -5, 4, -4]) == True
'''
    },
    {
        "task_id": "humaneval/HumanEval_4",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "mean_absolute_deviation",
        "prompt": '''from typing import List

def mean_absolute_deviation(numbers: List[float]) -> float:
    """ For a given list of input numbers, calculate Mean Absolute Deviation
    around the mean of this dataset.
    Mean Absolute Deviation is the average absolute difference between each
    element and a centerpoint (mean in this case):
    MAD = average |x - x_mean|
    >>> mean_absolute_deviation([1.0, 2.0, 3.0, 4.0])
    1.0
    """
''',
        "reference_solution": '''    mean = sum(numbers) / len(numbers)
    return sum(abs(x - mean) for x in numbers) / len(numbers)
''',
        "tests": '''def check(candidate):
    assert abs(candidate([1.0, 2.0, 3.0]) - 2.0/3.0) < 1e-6
    assert abs(candidate([1.0, 2.0, 3.0, 4.0]) - 1.0) < 1e-6
    assert abs(candidate([1.0, 2.0, 3.0, 4.0, 5.0]) - 6.0/5.0) < 1e-6
'''
    },
    {
        "task_id": "humaneval/HumanEval_5",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "intersperse",
        "prompt": '''from typing import List

def intersperse(numbers: List[int], delimeter: int) -> List[int]:
    """ Insert a number 'delimeter' between every two consecutive elements of input list `numbers'
    >>> intersperse([], 4)
    []
    >>> intersperse([1, 2, 3], 4)
    [1, 4, 2, 4, 3]
    """
''',
        "reference_solution": '''    if not numbers:
        return []
    result = []
    for n in numbers[:-1]:
        result.append(n)
        result.append(delimeter)
    result.append(numbers[-1])
    return result
''',
        "tests": '''def check(candidate):
    assert candidate([], 7) == []
    assert candidate([5, 6, 3, 2], 8) == [5, 8, 6, 8, 3, 8, 2]
    assert candidate([2, 2, 2], 2) == [2, 2, 2, 2, 2]
'''
    },
    {
        "task_id": "humaneval/HumanEval_6",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "parse_nested_parens",
        "prompt": '''from typing import List

def parse_nested_parens(paren_string: str) -> List[int]:
    """ Input to this function is a string represented multiple groups for nested parentheses separated by spaces.
    For each group, output the deepest level of nesting of parentheses.
    E.g. (()()) has maximum two levels of nesting while ((())) has three.

    >>> parse_nested_parens('(()()) ((())) () ((())()())')
    [2, 3, 1, 3]
    """
''',
        "reference_solution": '''    def parse_paren_group(s):
        depth = 0
        max_depth = 0
        for c in s:
            if c == '(':
                depth += 1
                max_depth = max(depth, max_depth)
            elif c == ')':
                depth -= 1
        return max_depth

    return [parse_paren_group(x) for x in paren_string.split(' ') if x]
''',
        "tests": '''def check(candidate):
    assert candidate('(()()) ((())) () ((())()())') == [2, 3, 1, 3]
    assert candidate('() (()) ((())) (((())))') == [1, 2, 3, 4]
    assert candidate('(()(())((())))') == [4]
'''
    },
    {
        "task_id": "humaneval/HumanEval_7",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "filter_by_substring",
        "prompt": '''from typing import List

def filter_by_substring(strings: List[str], substring: str) -> List[str]:
    """ Filter an input list of strings only for ones that contain given substring
    >>> filter_by_substring([], 'a')
    []
    >>> filter_by_substring(['abc', 'bac', 'cba', 'array'], 'a')
    ['abc', 'bac', 'cba', 'array']
    """
''',
        "reference_solution": '''    return [x for x in strings if substring in x]
''',
        "tests": '''def check(candidate):
    assert candidate([], 'john') == []
    assert candidate(['xxx', 'asd', 'xxy', 'john doe', 'xxxAAA', 'xxx'], 'xxx') == ['xxx', 'xxxAAA', 'xxx']
    assert candidate(['grunt', 'armstrong', 'all'], 'arm') == ['armstrong']
'''
    },
    {
        "task_id": "humaneval/HumanEval_8",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "sum_product",
        "prompt": '''from typing import List, Tuple

def sum_product(numbers: List[int]) -> Tuple[int, int]:
    """ For a given list of integers, return a tuple consisting of a sum and a product of all the integers in a list.
    Empty sum should be equal to 0 and empty product should be equal to 1.
    >>> sum_product([])
    (0, 1)
    >>> sum_product([1, 2, 3, 4])
    (10, 24)
    """
''',
        "reference_solution": '''    sum_value = 0
    prod_value = 1
    for n in numbers:
        sum_value += n
        prod_value *= n
    return sum_value, prod_value
''',
        "tests": '''def check(candidate):
    assert candidate([]) == (0, 1)
    assert candidate([1, 1, 1]) == (3, 1)
    assert candidate([100, 0]) == (100, 0)
    assert candidate([3, 5, 7]) == (15, 105)
    assert candidate([10]) == (10, 10)
'''
    },
    {
        "task_id": "humaneval/HumanEval_9",
        "source": TaskSource.HUMANEVAL,
        "entry_point": "rolling_max",
        "prompt": '''from typing import List

def rolling_max(numbers: List[int]) -> List[int]:
    """ From a given list of integers, generate a list of rolling maximum element found until given moment
    in the sequence.
    >>> rolling_max([1, 2, 3, 2, 3, 4, 2])
    [1, 2, 3, 3, 3, 4, 4]
    """
''',
        "reference_solution": '''    running_max = None
    result = []
    for n in numbers:
        if running_max is None:
            running_max = n
        else:
            running_max = max(running_max, n)
        result.append(running_max)
    return result
''',
        "tests": '''def check(candidate):
    assert candidate([]) == []
    assert candidate([1, 2, 3, 4]) == [1, 2, 3, 4]
    assert candidate([4, 3, 2, 1]) == [4, 4, 4, 4]
    assert candidate([3, 2, 3, 100, 3]) == [3, 3, 3, 100, 100]
'''
    },
    {
        "task_id": "mbpp/mbpp_1",
        "source": TaskSource.MBPP,
        "entry_point": "min_cost_path",
        "prompt": '''def min_cost_path(cost):
    """ Write a function to find the minimum cost path in a given cost matrix.
    >>> min_cost_path([[1, 2, 3], [4, 8, 2], [1, 5, 3]])
    8
    """
''',
        "reference_solution": '''    R = len(cost)
    C = len(cost[0])
    tc = [[0 for x in range(C)] for x in range(R)]
    tc[0][0] = cost[0][0]
    for i in range(1, R):
        tc[i][0] = tc[i-1][0] + cost[i][0]
    for j in range(1, C):
        tc[0][j] = tc[0][j-1] + cost[0][j]
    for i in range(1, R):
        for j in range(1, C):
            tc[i][j] = min(tc[i-1][j-1], tc[i-1][j], tc[i][j-1]) + cost[i][j]
    return tc[R-1][C-1]
''',
        "tests": '''def check(candidate):
    assert candidate([[1, 2, 3], [4, 8, 2], [1, 5, 3]]) == 8
    assert candidate([[2, 3, 4], [5, 9, 3], [2, 6, 4]]) == 12
    assert candidate([[3, 4, 5], [6, 10, 4], [3, 7, 5]]) == 16
'''
    },
    {
        "task_id": "mbpp/mbpp_3",
        "source": TaskSource.MBPP,
        "entry_point": "is_not_prime",
        "prompt": '''def is_not_prime(n: int) -> bool:
    """ Write a python function to identify non-prime numbers.
    >>> is_not_prime(2)
    False
    >>> is_not_prime(10)
    True
    """
''',
        "reference_solution": '''    import math
    if n <= 1:
        return True
    for i in range(2, int(math.isqrt(n)) + 1):
        if n % i == 0:
            return True
    return False
''',
        "tests": '''def check(candidate):
    assert candidate(2) == False
    assert candidate(10) == True
    assert candidate(35) == True
    assert candidate(37) == False
'''
    }
]

def main():
    with get_session() as session:
        updated = 0
        for item in CANONICAL_TASKS:
            task = session.get(Task, item["task_id"])
            if task:
                task.prompt = item["prompt"]
                task.reference_solution = item["reference_solution"]
                task.tests = item["tests"]
                task.entry_point = item["entry_point"]
                updated += 1
            else:
                task = Task(
                    task_id=item["task_id"],
                    source=item["source"],
                    prompt=item["prompt"],
                    reference_solution=item["reference_solution"],
                    tests=item["tests"],
                    entry_point=item["entry_point"],
                )
                session.add(task)
                updated += 1
        session.commit()
        print(f"Successfully enriched {updated} benchmark tasks with canonical prompts and reference solutions.")

if __name__ == "__main__":
    main()
