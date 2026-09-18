import sys
import os
import pytest

# Add the workspace directory to the Python path so we can import the student's code
sys.path.insert(0, "/workspace")

def test_missing_return():
    """
    Test that the calculate_sum function returns the correct sum instead of None.
    The student is expected to provide a file named `calculator.py` with `calculate_sum(a, b)`.
    """
    try:
        from calculator import calculate_sum
    except ImportError:
        pytest.fail("Could not import 'calculate_sum' from 'calculator.py'. Did you create the file?")

    # Test cases
    result = calculate_sum(2, 3)
    assert result == 5, f"Expected 5, but got {result}. Did you forget the return statement?"

    result = calculate_sum(-1, 1)
    assert result == 0, f"Expected 0, but got {result}."

    result = calculate_sum(100, 200)
    assert result == 300, f"Expected 300, but got {result}."
