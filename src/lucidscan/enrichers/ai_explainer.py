"""AI-powered enricher that adds LLM-generated explanations to issues.

This enricher uses LangChain to call LLM providers (OpenAI, Anthropic, Ollama)
and generate human-readable explanations for security issues.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from lucidscan.enrichers.base import EnricherPlugin
from lucidscan.core.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from lucidscan.config.models import AIConfig
    from lucidscan.core.models import ScanContext, UnifiedIssue
    from lucidscan.enrichers.ai.cache import AIExplanationCache

LOGGER = get_logger(__name__)


class AIExplainerEnricher(EnricherPlugin):
    """Enricher that adds AI-generated explanations to security issues.

    Features:
    - Uses LangChain for provider abstraction (OpenAI, Anthropic, Ollama)
    - Implements per-issue caching at ~/.lucidscan/cache/ai/
    - Stores explanations in scanner_metadata["ai_explanation"]
    - Never modifies severity levels or original issue data
    - Gracefully handles failures (issues pass through unchanged)

    Configuration:
        ai:
          enabled: true  # Or use --ai flag
          provider: openai  # openai, anthropic, ollama
          model: gpt-4o-mini  # Optional, uses defaults
          api_key: ${OPENAI_API_KEY}
          send_code_snippets: true
          cache_enabled: true
    """

    def __init__(self) -> None:
        """Initialize the AI explainer enricher."""
        self._llm: Optional["BaseChatModel"] = None
        self._cache: Optional["AIExplanationCache"] = None
        self._config: Optional["AIConfig"] = None

    @property
    def name(self) -> str:
        """Return the enricher identifier."""
        return "ai_explainer"

    def enrich(
        self,
        issues: List["UnifiedIssue"],
        context: "ScanContext",
    ) -> List["UnifiedIssue"]:
        """Add AI explanations to issues.

        Args:
            issues: List of issues to enrich.
            context: Scan context with configuration.

        Returns:
            Issues with AI explanations added to scanner_metadata.
        """
        # Get AI config from context
        ai_config = getattr(context.config, "ai", None)
        if not ai_config or not ai_config.enabled:
            LOGGER.debug("AI enrichment disabled, skipping")
            return issues

        self._config = ai_config

        if not issues:
            LOGGER.debug("No issues to enrich")
            return issues

        # Initialize LLM lazily
        if not self._initialize_llm():
            return issues

        # Initialize cache if enabled
        if ai_config.cache_enabled:
            self._initialize_cache()

        # Process each issue
        enriched_count = 0
        cached_count = 0
        failed_count = 0

        LOGGER.info(f"Generating AI explanations for {len(issues)} issues...")

        for issue in issues:
            explanation, from_cache = self._get_explanation(issue)
            if explanation:
                issue.scanner_metadata["ai_explanation"] = explanation
                issue.scanner_metadata["ai_model"] = self._get_model_name()
                enriched_count += 1
                if from_cache:
                    cached_count += 1
            else:
                failed_count += 1

        LOGGER.info(
            f"AI enrichment complete: {enriched_count}/{len(issues)} issues "
            f"({cached_count} from cache, {failed_count} failed)"
        )

        return issues

    def _initialize_llm(self) -> bool:
        """Initialize LLM provider.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self._llm is not None:
            return True

        try:
            from lucidscan.enrichers.ai.providers import get_llm, ProviderError

            self._llm = get_llm(self._config)
            LOGGER.debug(f"Initialized {self._config.provider} LLM provider")
            return True
        except ProviderError as e:
            LOGGER.error(f"Failed to initialize AI provider: {e}")
            return False
        except Exception as e:
            LOGGER.error(f"Unexpected error initializing AI: {e}")
            return False

    def _initialize_cache(self) -> None:
        """Initialize cache if not already done."""
        if self._cache is not None:
            return

        from lucidscan.enrichers.ai.cache import AIExplanationCache

        self._cache = AIExplanationCache()
        LOGGER.debug(f"AI cache initialized at {self._cache.cache_dir}")

    def _get_explanation(
        self, issue: "UnifiedIssue"
    ) -> Tuple[Optional[str], bool]:
        """Get AI explanation for an issue.

        Args:
            issue: The issue to explain.

        Returns:
            Tuple of (explanation, from_cache). explanation is None on failure.
        """
        # Check cache first
        cache_key = self._compute_cache_key(issue)

        if self._cache and cache_key:
            cached = self._cache.get(cache_key)
            if cached:
                LOGGER.debug(f"Cache hit for issue {issue.id}")
                return cached.explanation, True

        # Generate new explanation
        try:
            explanation = self._generate_explanation(issue)

            # Store in cache
            if self._cache and cache_key and explanation:
                from lucidscan.enrichers.ai.cache import create_cache_entry

                entry = create_cache_entry(
                    explanation=explanation,
                    model=self._get_model_name(),
                    prompt_version=self._config.prompt_version,
                )
                self._cache.set(cache_key, entry)

            return explanation, False

        except Exception as e:
            LOGGER.warning(f"Failed to generate explanation for {issue.id}: {e}")
            return None, False

    def _generate_explanation(self, issue: "UnifiedIssue") -> Optional[str]:
        """Generate explanation using LLM.

        Args:
            issue: The issue to explain.

        Returns:
            Generated explanation text, or None on failure.
        """
        from lucidscan.enrichers.ai.prompts import SYSTEM_PROMPT, format_prompt

        # Import LangChain message types lazily
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
        except ImportError:
            LOGGER.error("langchain-core is required for AI explanations")
            return None

        user_prompt = format_prompt(
            issue,
            include_code=self._config.send_code_snippets,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self._llm.invoke(messages)
        return response.content.strip()

    def _compute_cache_key(self, issue: "UnifiedIssue") -> Optional[str]:
        """Compute cache key for an issue.

        Args:
            issue: The issue to compute key for.

        Returns:
            Cache key string, or None if cache is disabled.
        """
        if not self._cache:
            return None

        return self._cache.compute_cache_key(
            issue_id=issue.id,
            issue_title=issue.title,
            issue_description=issue.description,
            code_snippet=issue.code_snippet,
            model=self._get_model_name(),
            prompt_version=self._config.prompt_version,
            include_snippet=self._config.send_code_snippets,
        )

    def _get_model_name(self) -> str:
        """Get the model name being used.

        Returns:
            Model name from config or default for provider.
        """
        from lucidscan.enrichers.ai.providers import get_model_name

        return get_model_name(self._config)
