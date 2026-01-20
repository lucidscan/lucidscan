"""Main application with intentional issues for testing."""

import os  # F401: unused import
import sys  # F401: unused import
import subprocess


def get_user_data(user_id):
    """Get user data - has SQL injection vulnerability for SAST testing."""
    # SAST: SQL injection vulnerability
    query = "SELECT * FROM users WHERE id = " + user_id
    return query


def run_command(cmd: str) -> str:
    """Run command - has command injection vulnerability for SAST testing."""
    # SAST: Command injection vulnerability
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout


def process_data(data):
    """Process data with type issues."""
    # Type error: no type annotations
    return data * 2
