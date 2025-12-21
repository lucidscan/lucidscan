"""Unit tests for AI explanation cache."""

from pathlib import Path

import pytest

from lucidscan.enrichers.ai.cache import (
    AIExplanationCache,
    CacheEntry,
    create_cache_entry,
)


class TestAIExplanationCache:
    """Tests for AIExplanationCache."""

    @pytest.fixture
    def cache(self, tmp_path: Path) -> AIExplanationCache:
        """Create a cache with a temporary directory."""
        return AIExplanationCache(cache_dir=tmp_path / "ai_cache")

    def test_cache_miss_returns_none(self, cache: AIExplanationCache) -> None:
        """Test that cache miss returns None."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_cache_set_and_get(self, cache: AIExplanationCache) -> None:
        """Test storing and retrieving cache entries."""
        entry = CacheEntry(
            explanation="Test explanation",
            model="gpt-4",
            prompt_version="v1",
            created_at="2024-01-01T00:00:00Z",
        )
        cache.set("test_key", entry)

        result = cache.get("test_key")
        assert result is not None
        assert result.explanation == "Test explanation"
        assert result.model == "gpt-4"
        assert result.prompt_version == "v1"
        assert result.created_at == "2024-01-01T00:00:00Z"

    def test_cache_key_computation_is_deterministic(
        self, cache: AIExplanationCache
    ) -> None:
        """Test that cache key computation is deterministic."""
        key1 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="SQL Injection",
            issue_description="User input is not sanitized",
            code_snippet="query = f'SELECT * FROM users WHERE id={user_id}'",
            model="gpt-4",
            prompt_version="v1",
        )
        key2 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="SQL Injection",
            issue_description="User input is not sanitized",
            code_snippet="query = f'SELECT * FROM users WHERE id={user_id}'",
            model="gpt-4",
            prompt_version="v1",
        )
        assert key1 == key2

    def test_cache_key_changes_with_content(
        self, cache: AIExplanationCache
    ) -> None:
        """Test that cache key changes when content changes."""
        key1 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="SQL Injection",
            issue_description="Description 1",
            code_snippet=None,
            model="gpt-4",
            prompt_version="v1",
        )
        key2 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="SQL Injection",
            issue_description="Description 2",  # Different
            code_snippet=None,
            model="gpt-4",
            prompt_version="v1",
        )
        assert key1 != key2

    def test_cache_key_changes_with_model(
        self, cache: AIExplanationCache
    ) -> None:
        """Test that cache key changes when model changes."""
        key1 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet=None,
            model="gpt-4",
            prompt_version="v1",
        )
        key2 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet=None,
            model="claude-3",  # Different
            prompt_version="v1",
        )
        assert key1 != key2

    def test_cache_key_changes_with_prompt_version(
        self, cache: AIExplanationCache
    ) -> None:
        """Test that cache key changes when prompt version changes."""
        key1 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet=None,
            model="gpt-4",
            prompt_version="v1",
        )
        key2 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet=None,
            model="gpt-4",
            prompt_version="v2",  # Different
        )
        assert key1 != key2

    def test_cache_key_with_code_snippet(
        self, cache: AIExplanationCache
    ) -> None:
        """Test that code snippet affects cache key when included."""
        key1 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet="code_a",
            model="gpt-4",
            prompt_version="v1",
            include_snippet=True,
        )
        key2 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet="code_b",  # Different
            model="gpt-4",
            prompt_version="v1",
            include_snippet=True,
        )
        assert key1 != key2

    def test_cache_key_without_code_snippet(
        self, cache: AIExplanationCache
    ) -> None:
        """Test that code snippet is ignored when include_snippet=False."""
        key1 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet="code_a",
            model="gpt-4",
            prompt_version="v1",
            include_snippet=False,
        )
        key2 = cache.compute_cache_key(
            issue_id="issue-1",
            issue_title="Title",
            issue_description="Description",
            code_snippet="code_b",  # Different but ignored
            model="gpt-4",
            prompt_version="v1",
            include_snippet=False,
        )
        assert key1 == key2

    def test_cache_handles_corrupted_file(
        self, cache: AIExplanationCache, tmp_path: Path
    ) -> None:
        """Test that cache handles corrupted JSON gracefully."""
        # Create a corrupted cache file
        cache_dir = tmp_path / "ai_cache" / "ab"
        cache_dir.mkdir(parents=True)
        corrupted_file = cache_dir / "ab123456.json"
        corrupted_file.write_text("not valid json {{{")

        result = cache.get("ab123456")
        assert result is None  # Should return None, not raise

    def test_cache_clear(self, cache: AIExplanationCache) -> None:
        """Test clearing the cache."""
        # Add some entries
        for i in range(3):
            entry = CacheEntry(
                explanation=f"Explanation {i}",
                model="gpt-4",
                prompt_version="v1",
                created_at="2024-01-01T00:00:00Z",
            )
            cache.set(f"key_{i:064x}", entry)

        # Clear cache
        count = cache.clear()
        assert count == 3

        # Verify entries are gone
        for i in range(3):
            assert cache.get(f"key_{i:064x}") is None


class TestCreateCacheEntry:
    """Tests for create_cache_entry helper."""

    def test_creates_entry_with_timestamp(self) -> None:
        """Test that create_cache_entry sets current timestamp."""
        entry = create_cache_entry(
            explanation="Test",
            model="gpt-4",
            prompt_version="v1",
        )
        assert entry.explanation == "Test"
        assert entry.model == "gpt-4"
        assert entry.prompt_version == "v1"
        assert entry.created_at  # Should have timestamp
        assert "T" in entry.created_at  # ISO format
