"""Unit tests for AI explainer enricher."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidscan.config.models import AIConfig, LucidScanConfig
from lucidscan.core.models import ScanContext, ScanDomain, Severity, UnifiedIssue
from lucidscan.enrichers.ai_explainer import AIExplainerEnricher


class TestAIExplainerEnricher:
    """Tests for AIExplainerEnricher class."""

    @pytest.fixture
    def enricher(self) -> AIExplainerEnricher:
        """Create an AIExplainerEnricher instance."""
        return AIExplainerEnricher()

    @pytest.fixture
    def sample_issues(self) -> list[UnifiedIssue]:
        """Create sample issues for testing."""
        return [
            UnifiedIssue(
                id="CVE-2024-001",
                scanner=ScanDomain.SCA,
                source_tool="trivy",
                severity=Severity.HIGH,
                title="SQL Injection",
                description="Vulnerable to SQL injection",
                dependency="sqlparse@0.4.0",
            ),
            UnifiedIssue(
                id="SAST-001",
                scanner=ScanDomain.SAST,
                source_tool="opengrep",
                severity=Severity.MEDIUM,
                title="Hardcoded Secret",
                description="Secret found in code",
                file_path=Path("src/config.py"),
                line_start=10,
            ),
        ]

    @pytest.fixture
    def context_ai_disabled(self, tmp_path: Path) -> ScanContext:
        """Create context with AI disabled."""
        config = LucidScanConfig(
            ai=AIConfig(enabled=False),
        )
        return ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
            config=config,
        )

    @pytest.fixture
    def context_ai_enabled(self, tmp_path: Path) -> ScanContext:
        """Create context with AI enabled."""
        config = LucidScanConfig(
            ai=AIConfig(
                enabled=True,
                provider="openai",
                model="gpt-4",
                api_key="test-key",
                cache_enabled=False,
            ),
        )
        return ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
            config=config,
        )

    def test_name_property(self, enricher: AIExplainerEnricher) -> None:
        """Test enricher name property."""
        assert enricher.name == "ai_explainer"

    def test_skips_when_ai_disabled(
        self,
        enricher: AIExplainerEnricher,
        sample_issues: list[UnifiedIssue],
        context_ai_disabled: ScanContext,
    ) -> None:
        """Test enricher skips processing when AI is disabled."""
        result = enricher.enrich(sample_issues, context_ai_disabled)
        assert result == sample_issues
        # No AI explanation should be added
        for issue in result:
            assert "ai_explanation" not in issue.scanner_metadata

    def test_skips_when_no_config(
        self,
        enricher: AIExplainerEnricher,
        sample_issues: list[UnifiedIssue],
        tmp_path: Path,
    ) -> None:
        """Test enricher skips when no config present."""
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
            config=None,
        )
        result = enricher.enrich(sample_issues, context)
        assert result == sample_issues

    def test_returns_empty_list_unchanged(
        self,
        enricher: AIExplainerEnricher,
        context_ai_enabled: ScanContext,
    ) -> None:
        """Test enricher handles empty issue list."""
        result = enricher.enrich([], context_ai_enabled)
        assert result == []

    @patch("lucidscan.enrichers.ai.providers.get_llm")
    def test_adds_explanation_to_issues(
        self,
        mock_get_llm: MagicMock,
        enricher: AIExplainerEnricher,
        sample_issues: list[UnifiedIssue],
        context_ai_enabled: ScanContext,
    ) -> None:
        """Test enricher adds AI explanation to issues."""
        # Mock LLM response
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is a test explanation."
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        # Mock langchain_core.messages imports
        mock_system_msg = MagicMock()
        mock_human_msg = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "langchain_core": MagicMock(),
                "langchain_core.messages": MagicMock(
                    SystemMessage=mock_system_msg,
                    HumanMessage=mock_human_msg,
                ),
            },
        ):
            result = enricher.enrich(sample_issues, context_ai_enabled)

        assert len(result) == 2
        for issue in result:
            assert "ai_explanation" in issue.scanner_metadata
            assert issue.scanner_metadata["ai_explanation"] == "This is a test explanation."
            assert "ai_model" in issue.scanner_metadata

    @patch("lucidscan.enrichers.ai.providers.get_llm")
    def test_handles_llm_failure_gracefully(
        self,
        mock_get_llm: MagicMock,
        enricher: AIExplainerEnricher,
        sample_issues: list[UnifiedIssue],
        context_ai_enabled: ScanContext,
    ) -> None:
        """Test enricher handles LLM failures gracefully."""
        # Mock LLM to raise exception
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API error")
        mock_get_llm.return_value = mock_llm

        result = enricher.enrich(sample_issues, context_ai_enabled)

        # Issues should be returned unchanged (no explanation)
        assert len(result) == 2
        for issue in result:
            assert "ai_explanation" not in issue.scanner_metadata

    @patch("lucidscan.enrichers.ai.providers.get_llm")
    def test_never_modifies_severity(
        self,
        mock_get_llm: MagicMock,
        enricher: AIExplainerEnricher,
        sample_issues: list[UnifiedIssue],
        context_ai_enabled: ScanContext,
    ) -> None:
        """Test enricher never modifies issue severity."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Explanation"
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        original_severities = [issue.severity for issue in sample_issues]
        result = enricher.enrich(sample_issues, context_ai_enabled)

        # Severity should be unchanged
        for i, issue in enumerate(result):
            assert issue.severity == original_severities[i]

    @patch("lucidscan.enrichers.ai.providers.get_llm")
    def test_handles_provider_init_failure(
        self,
        mock_get_llm: MagicMock,
        enricher: AIExplainerEnricher,
        sample_issues: list[UnifiedIssue],
        context_ai_enabled: ScanContext,
    ) -> None:
        """Test enricher handles provider initialization failure."""
        from lucidscan.enrichers.ai.providers import ProviderError

        mock_get_llm.side_effect = ProviderError("Provider init failed")

        result = enricher.enrich(sample_issues, context_ai_enabled)

        # Issues should be returned unchanged
        assert result == sample_issues

    @patch("lucidscan.enrichers.ai.providers.get_llm")
    @patch("lucidscan.enrichers.ai.cache.AIExplanationCache")
    def test_uses_cache_when_enabled(
        self,
        mock_cache_class: MagicMock,
        mock_get_llm: MagicMock,
        enricher: AIExplainerEnricher,
        sample_issues: list[UnifiedIssue],
        tmp_path: Path,
    ) -> None:
        """Test enricher uses cache when enabled."""
        config = LucidScanConfig(
            ai=AIConfig(
                enabled=True,
                provider="openai",
                model="gpt-4",
                cache_enabled=True,
            ),
        )
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
            config=config,
        )

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Explanation"
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # Cache miss
        mock_cache_class.return_value = mock_cache

        # Mock langchain_core.messages imports
        with patch.dict(
            "sys.modules",
            {
                "langchain_core": MagicMock(),
                "langchain_core.messages": MagicMock(
                    SystemMessage=MagicMock(),
                    HumanMessage=MagicMock(),
                ),
            },
        ):
            enricher.enrich(sample_issues[:1], context)

        # Should have tried to get from cache
        mock_cache.get.assert_called()
        # Should have stored in cache
        mock_cache.set.assert_called()
