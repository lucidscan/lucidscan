"""LangChain provider initialization with lazy loading.

Initializes LLM providers only when AI enrichment is enabled.
Supports OpenAI, Anthropic, and Ollama via LangChain packages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lucidscan.core.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from lucidscan.config.models import AIConfig

LOGGER = get_logger(__name__)

# Default models per provider
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku-20240307",
    "ollama": "llama3.2",
}


class ProviderError(Exception):
    """Error initializing or using LLM provider."""

    pass


def get_llm(config: "AIConfig") -> "BaseChatModel":
    """Initialize and return LangChain LLM based on config.

    Lazy-loads provider packages to avoid import overhead when AI is disabled.

    Args:
        config: AI configuration with provider, model, and credentials.

    Returns:
        Configured LangChain chat model.

    Raises:
        ProviderError: If provider is unknown or initialization fails.
    """
    provider = config.provider.lower()
    model = config.model or DEFAULT_MODELS.get(provider)

    if not model:
        raise ProviderError(
            f"No model specified and no default for provider: {provider}"
        )

    LOGGER.debug(f"Initializing {provider} provider with model {model}")

    if provider == "openai":
        return _init_openai(config, model)
    elif provider == "anthropic":
        return _init_anthropic(config, model)
    elif provider == "ollama":
        return _init_ollama(config, model)
    else:
        raise ProviderError(f"Unknown AI provider: {provider}")


def _init_openai(config: "AIConfig", model: str) -> "BaseChatModel":
    """Initialize OpenAI provider.

    Args:
        config: AI configuration.
        model: Model name to use.

    Returns:
        Configured ChatOpenAI instance.

    Raises:
        ProviderError: If langchain-openai is not installed.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ProviderError(
            "OpenAI provider requires langchain-openai. "
            "Install with: pip install lucidscan[ai-openai]"
        ) from e

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }

    if config.api_key:
        kwargs["api_key"] = config.api_key
    # Otherwise uses OPENAI_API_KEY env var

    if config.base_url:
        kwargs["base_url"] = config.base_url

    return ChatOpenAI(**kwargs)


def _init_anthropic(config: "AIConfig", model: str) -> "BaseChatModel":
    """Initialize Anthropic provider.

    Args:
        config: AI configuration.
        model: Model name to use.

    Returns:
        Configured ChatAnthropic instance.

    Raises:
        ProviderError: If langchain-anthropic is not installed.
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise ProviderError(
            "Anthropic provider requires langchain-anthropic. "
            "Install with: pip install lucidscan[ai-anthropic]"
        ) from e

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }

    if config.api_key:
        kwargs["api_key"] = config.api_key
    # Otherwise uses ANTHROPIC_API_KEY env var

    if config.base_url:
        kwargs["base_url"] = config.base_url

    return ChatAnthropic(**kwargs)


def _init_ollama(config: "AIConfig", model: str) -> "BaseChatModel":
    """Initialize Ollama provider (local LLM).

    Args:
        config: AI configuration.
        model: Model name to use.

    Returns:
        Configured ChatOllama instance.

    Raises:
        ProviderError: If langchain-ollama is not installed.
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError as e:
        raise ProviderError(
            "Ollama provider requires langchain-ollama. "
            "Install with: pip install lucidscan[ai-ollama]"
        ) from e

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": config.temperature,
    }

    if config.base_url:
        kwargs["base_url"] = config.base_url
    # Default: http://localhost:11434

    return ChatOllama(**kwargs)


def get_model_name(config: "AIConfig") -> str:
    """Get the model name being used.

    Args:
        config: AI configuration.

    Returns:
        Model name (from config or default for provider).
    """
    if config.model:
        return config.model
    return DEFAULT_MODELS.get(config.provider.lower(), "unknown")
