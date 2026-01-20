"""Models with type errors for testing."""

from typing import Optional


class User:
    """User model with type errors."""

    def __init__(self, name: str, age: int) -> None:
        self.name = name
        self.age = age

    def get_info(self) -> str:
        # Type error: returning int instead of str
        return self.age

    def set_age(self, age: str) -> None:
        # Type error: assigning str to int field
        self.age = age


def create_user(data: dict) -> User:
    """Create user with type mismatch."""
    # Type error: passing wrong types
    return User(name=123, age="twenty")


def get_optional_user() -> Optional[User]:
    """Return optional user."""
    return None


def use_optional() -> str:
    """Use optional without checking - type error."""
    user = get_optional_user()
    # Type error: accessing attribute on Optional without check
    return user.name
