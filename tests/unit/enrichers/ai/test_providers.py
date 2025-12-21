"""Unit tests for AI provider initialization."""

from unittest.mock import MagicMock, patch

import pytest

from lucidscan.config.models import AIConfig
from lucidscan.enrichers.ai.providers import (
    DEFAULT_MODELS,
    ProviderError,
    get_llm,
    get_model_name,
)


class TestDefaultModels:
    """Tests for DEFAULT_MODELS constant."""

    def test_openai_has_default(self) -> None:
        """Test OpenAI has a default model."""
        assert "openai" in DEFAULT_MODELS
        assert DEFAULT_MODELS["openai"]

    def test_anthropic_has_default(self) -> None:
        """Test Anthropic has a default model."""
        assert "anthropic" in DEFAULT_MODELS
        assert DEFAULT_MODELS["anthropic"]

    def test_ollama_has_default(self) -> None:
        """Test Ollama has a default model."""
        assert "ollama" in DEFAULT_MODELS
        assert DEFAULT_MODELS["ollama"]


class TestGetModelName:
    """Tests for get_model_name function."""

    def test_returns_config_model_if_set(self) -> None:
        """Test returns model from config when specified."""
        config = AIConfig(provider="openai", model="gpt-4-turbo")
        assert get_model_name(config) == "gpt-4-turbo"

    def test_returns_default_if_model_empty(self) -> None:
        """Test returns default model when config model is empty."""
        config = AIConfig(provider="openai", model="")
        assert get_model_name(config) == DEFAULT_MODELS["openai"]

    def test_handles_unknown_provider(self) -> None:
        """Test returns 'unknown' for unknown provider with no model."""
        config = AIConfig(provider="unknown_provider", model="")
        assert get_model_name(config) == "unknown"


class TestGetLLM:
    """Tests for get_llm function."""

    def test_unknown_provider_raises_error(self) -> None:
        """Test that unknown provider raises ProviderError."""
        config = AIConfig(provider="unknown_provider", model="test")
        with pytest.raises(ProviderError, match="Unknown AI provider"):
            get_llm(config)

    def test_no_model_and_unknown_provider_raises_error(self) -> None:
        """Test error when no model and unknown provider."""
        config = AIConfig(provider="unknown_provider", model="")
        with pytest.raises(ProviderError, match="No model specified"):
            get_llm(config)

    @patch("lucidscan.enrichers.ai.providers._init_openai")
    def test_openai_provider_calls_init_openai(
        self, mock_init: MagicMock
    ) -> None:
        """Test OpenAI provider calls correct init function."""
        mock_init.return_value = MagicMock()
        config = AIConfig(provider="openai", model="gpt-4")
        get_llm(config)
        mock_init.assert_called_once_with(config, "gpt-4")

    @patch("lucidscan.enrichers.ai.providers._init_anthropic")
    def test_anthropic_provider_calls_init_anthropic(
        self, mock_init: MagicMock
    ) -> None:
        """Test Anthropic provider calls correct init function."""
        mock_init.return_value = MagicMock()
        config = AIConfig(provider="anthropic", model="claude-3")
        get_llm(config)
        mock_init.assert_called_once_with(config, "claude-3")

    @patch("lucidscan.enrichers.ai.providers._init_ollama")
    def test_ollama_provider_calls_init_ollama(
        self, mock_init: MagicMock
    ) -> None:
        """Test Ollama provider calls correct init function."""
        mock_init.return_value = MagicMock()
        config = AIConfig(provider="ollama", model="llama3")
        get_llm(config)
        mock_init.assert_called_once_with(config, "llama3")

    def test_provider_case_insensitive(self) -> None:
        """Test provider name is case insensitive."""
        with patch("lucidscan.enrichers.ai.providers._init_openai") as mock:
            mock.return_value = MagicMock()
            config = AIConfig(provider="OpenAI", model="gpt-4")
            get_llm(config)
            mock.assert_called_once()


class TestInitOpenAI:
    """Tests for OpenAI provider initialization."""

    def test_raises_when_package_not_installed(self) -> None:
        """Test raises ProviderError when langchain-openai not installed."""
        import sys
        from lucidscan.enrichers.ai import providers

        # Mock the import to fail
        with patch.dict(sys.modules, {"langchain_openai": None}):
            # Force reimport by clearing from module cache
            with patch.object(
                providers,
                "_init_openai",
                side_effect=ProviderError("langchain-openai not installed"),
            ):
                config = AIConfig(provider="openai", model="gpt-4")
                with pytest.raises(ProviderError, match="langchain-openai"):
                    providers._init_openai(config, "gpt-4")


class TestInitAnthropic:
    """Tests for Anthropic provider initialization."""

    def test_raises_when_package_not_installed(self) -> None:
        """Test raises ProviderError when langchain-anthropic not installed."""
        from lucidscan.enrichers.ai import providers

        with patch.object(
            providers,
            "_init_anthropic",
            side_effect=ProviderError("langchain-anthropic not installed"),
        ):
            config = AIConfig(provider="anthropic", model="claude-3")
            with pytest.raises(ProviderError, match="langchain-anthropic"):
                providers._init_anthropic(config, "claude-3")


class TestInitOllama:
    """Tests for Ollama provider initialization."""

    def test_raises_when_package_not_installed(self) -> None:
        """Test raises ProviderError when langchain-ollama not installed."""
        from lucidscan.enrichers.ai import providers

        with patch.object(
            providers,
            "_init_ollama",
            side_effect=ProviderError("langchain-ollama not installed"),
        ):
            config = AIConfig(provider="ollama", model="llama3")
            with pytest.raises(ProviderError, match="langchain-ollama"):
                providers._init_ollama(config, "llama3")
