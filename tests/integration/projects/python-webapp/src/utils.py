"""Utilities with linting issues for testing."""

import json  # F401: unused import
import re  # F401: unused import


def calculate(x,y):  # E231: missing whitespace after comma
    """Calculate with formatting issues."""
    result=x+y  # E225: missing whitespace around operator
    return result


def unused_function():
    """This function is never called."""
    pass


class BadClass:
    """Class with issues."""

    def method(self):
        x = 1  # F841: local variable assigned but never used
        return True


def compare_types(a, b):
    """Comparison issues."""
    if a == None:  # E711: comparison to None
        return False
    if type(b) == str:  # E721: type comparison
        return True
    return a == b
