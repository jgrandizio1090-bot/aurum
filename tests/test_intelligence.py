from aurum_voice.intelligence import (
    DomainIntelligenceService,
    IntelligenceItem,
    _extract_keywords,
)


def test_extract_keywords_prefers_domain_terms() -> None:
    items = [
        IntelligenceItem(
            source="IRS",
            title="IRS updates retirement contribution thresholds",
            link="",
            published="",
            summary="Retirement planning updates and tax bracket adjustments.",
        ),
        IntelligenceItem(
            source="SEC",
            title="SEC risk alert on advisory compliance controls",
            link="",
            published="",
            summary="Advisers should strengthen compliance controls and disclosures.",
        ),
    ]
    keywords = _extract_keywords(items)
    assert "retirement" in keywords
    assert "advisory" in keywords


def test_build_context_handles_empty_snapshot() -> None:
    intelligence = DomainIntelligenceService()
    context = intelligence.build_context(max_chars=240)
    assert isinstance(context, str)
    assert len(context) > 0
