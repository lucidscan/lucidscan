"""Basic tests for the app."""

from src.app import process_data


def test_process_data():
    """Test process_data function."""
    assert process_data(5) == 10


def test_process_string():
    """Test process_data with string."""
    assert process_data("ab") == "abab"
