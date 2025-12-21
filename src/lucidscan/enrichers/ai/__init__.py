"""AI enrichment subpackage.

Provides LLM-powered explanations for security issues using LangChain.
"""

from lucidscan.enrichers.ai.cache import (
    AIExplanationCache,
    CacheEntry,
    create_cache_entry,
)
from lucidscan.enrichers.ai.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    format_prompt,
    get_prompt_template,
)
from lucidscan.enrichers.ai.providers import (
    DEFAULT_MODELS,
    ProviderError,
    get_llm,
    get_model_name,
)

__all__ = [
    # Cache
    "AIExplanationCache",
    "CacheEntry",
    "create_cache_entry",
    # Prompts
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "format_prompt",
    "get_prompt_template",
    # Providers
    "DEFAULT_MODELS",
    "ProviderError",
    "get_llm",
    "get_model_name",
]
