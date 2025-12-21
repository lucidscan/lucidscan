"""On-disk cache for AI explanations.

Caches AI-generated explanations to avoid redundant API calls.
Cache is stored at ~/.lucidscan/cache/ai/ with sharded directories.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lucidscan.bootstrap.paths import LucidscanPaths
from lucidscan.core.logging import get_logger

LOGGER = get_logger(__name__)

# Cache subdirectory under ~/.lucidscan/cache/
CACHE_SUBDIR = "ai"


@dataclass
class CacheEntry:
    """Cached AI explanation."""

    explanation: str
    model: str
    prompt_version: str
    created_at: str  # ISO format


class AIExplanationCache:
    """Manages on-disk cache for AI explanations.

    Cache structure:
        ~/.lucidscan/cache/ai/
            {hash_prefix}/
                {full_hash}.json

    Hash components:
        - issue.id
        - issue.title
        - issue.description
        - issue.code_snippet (if send_code_snippets=True)
        - model name
        - prompt_version
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """Initialize cache.

        Args:
            cache_dir: Optional custom cache directory. If not provided,
                       uses ~/.lucidscan/cache/ai/
        """
        if cache_dir:
            self._cache_dir = cache_dir
        else:
            paths = LucidscanPaths.default()
            self._cache_dir = paths.cache_dir / CACHE_SUBDIR

    @property
    def cache_dir(self) -> Path:
        """Get the cache directory."""
        return self._cache_dir

    def get(self, cache_key: str) -> Optional[CacheEntry]:
        """Get cached explanation by key.

        Args:
            cache_key: SHA256 hash key for the cached entry.

        Returns:
            CacheEntry if found and valid, None otherwise.
        """
        cache_path = self._get_cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return CacheEntry(
                explanation=data["explanation"],
                model=data["model"],
                prompt_version=data["prompt_version"],
                created_at=data["created_at"],
            )
        except (json.JSONDecodeError, KeyError, OSError) as e:
            LOGGER.warning(f"Failed to read cache entry {cache_key}: {e}")
            return None

    def set(self, cache_key: str, entry: CacheEntry) -> None:
        """Store explanation in cache.

        Args:
            cache_key: SHA256 hash key for the entry.
            entry: CacheEntry to store.
        """
        cache_path = self._get_cache_path(cache_key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "explanation": entry.explanation,
                        "model": entry.model,
                        "prompt_version": entry.prompt_version,
                        "created_at": entry.created_at,
                    },
                    f,
                    indent=2,
                )
        except OSError as e:
            LOGGER.warning(f"Failed to write cache entry {cache_key}: {e}")

    def compute_cache_key(
        self,
        issue_id: str,
        issue_title: str,
        issue_description: str,
        code_snippet: Optional[str],
        model: str,
        prompt_version: str,
        include_snippet: bool = True,
    ) -> str:
        """Compute deterministic cache key.

        The cache key is a SHA256 hash of the issue content and model info.
        This ensures cache invalidation when prompts change or models are updated.

        Args:
            issue_id: Unique issue identifier.
            issue_title: Issue title.
            issue_description: Issue description.
            code_snippet: Optional code snippet.
            model: Model name being used.
            prompt_version: Prompt template version.
            include_snippet: Whether to include code snippet in hash.

        Returns:
            SHA256 hash as hex string.
        """
        components = [
            issue_id,
            issue_title,
            issue_description,
            model,
            prompt_version,
        ]
        if include_snippet and code_snippet:
            components.append(code_snippet)

        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get file path for cache key (with prefix directory for sharding).

        Uses first 2 characters of hash as subdirectory to avoid
        filesystem performance issues with many files.

        Args:
            cache_key: SHA256 hash key.

        Returns:
            Path to cache file.
        """
        prefix = cache_key[:2]
        return self._cache_dir / prefix / f"{cache_key}.json"

    def clear(self) -> int:
        """Clear all cached entries.

        Returns:
            Number of entries cleared.
        """
        count = 0
        if not self._cache_dir.exists():
            return count

        for prefix_dir in self._cache_dir.iterdir():
            if prefix_dir.is_dir():
                for cache_file in prefix_dir.glob("*.json"):
                    try:
                        cache_file.unlink()
                        count += 1
                    except OSError:
                        pass
                # Remove empty prefix directory
                try:
                    prefix_dir.rmdir()
                except OSError:
                    pass

        return count


def create_cache_entry(explanation: str, model: str, prompt_version: str) -> CacheEntry:
    """Create a new cache entry with current timestamp.

    Args:
        explanation: AI-generated explanation text.
        model: Model name used for generation.
        prompt_version: Prompt template version.

    Returns:
        CacheEntry with current timestamp.
    """
    return CacheEntry(
        explanation=explanation,
        model=model,
        prompt_version=prompt_version,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
