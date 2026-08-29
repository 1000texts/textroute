"""The analyzer degrades rather than failing: an SMS must always reach review."""

from unittest.mock import MagicMock, patch

from src.core.providers.request_analyzer import RequestAnalysis, RequestAnalyzer

FALLBACK = RequestAnalysis(
    request_type="general",
    summary="Does anyone have an axe?",
    extracted_filters={},
    confidence=0.25,
    notes="keyword_fallback",
)


def test_disabled_analyzer_returns_the_keyword_fallback_untouched():
    analyzer = RequestAnalyzer(enabled=False)
    assert analyzer.analyze("Does anyone have an axe?", fallback=FALLBACK) is FALLBACK


def test_model_failure_degrades_to_keywords_rather_than_raising():
    """Ollama being down must not cost the group an inbound message."""
    analyzer = RequestAnalyzer(enabled=True)
    with patch(
        "src.ai.extraction.analyze_request_payload",
        side_effect=RuntimeError("ollama unreachable"),
    ):
        result = analyzer.analyze("Does anyone have an axe?", fallback=FALLBACK)

    assert result is FALLBACK
    assert result.notes == "analysis_failed_keyword_fallback"
    # No model name is how a reader tells a degraded result from a real one.
    assert result.used_model is False


def test_successful_analysis_carries_the_models_own_confidence():
    analyzer = RequestAnalyzer(enabled=True)
    intent = MagicMock(intent="request_borrow", confidence=0.82)
    extracted = MagicMock()
    extracted.model_dump.return_value = {"object": "axe", "time": "Saturday"}

    with (
        patch(
            "src.ai.extraction.analyze_request_payload",
            return_value=(intent, MagicMock(), extracted),
        ),
        patch.object(RequestAnalyzer, "_embed", return_value=[0.1] * 1024),
    ):
        result = analyzer.analyze("Does anyone have an axe?", fallback=FALLBACK)

    assert result.request_type == "request_borrow"
    assert result.confidence == 0.82
    assert result.extracted_filters == {"object": "axe", "time": "Saturday"}
    assert result.used_model is True
    assert len(result.embedding) == 1024


def test_a_wrong_width_embedding_is_dropped_not_stored():
    """The column is fixed-width for ivfflat, so a mismatch is a config error."""
    analyzer = RequestAnalyzer(enabled=True)
    embeddings = MagicMock()
    embeddings.embed_query.return_value = [0.1] * 1536

    with patch.dict("sys.modules", {}):
        with patch("src.ai.llm.EMBEDDINGS", embeddings):
            assert analyzer._embed("text") is None


def test_an_embedding_failure_leaves_the_request_usable():
    analyzer = RequestAnalyzer(enabled=True)
    embeddings = MagicMock()
    embeddings.embed_query.side_effect = RuntimeError("model not pulled")

    with patch("src.ai.llm.EMBEDDINGS", embeddings):
        assert analyzer._embed("text") is None


def test_summary_prefers_extracted_fields_over_raw_text():
    summary = RequestAnalyzer._summarize("request_borrow", {"object": "axe"}, "long...")
    assert summary == "request borrow: axe"


def test_summary_falls_back_to_the_message_when_nothing_was_extracted():
    body = "x" * 300
    assert RequestAnalyzer._summarize("general", {}, body) == body[:140]
