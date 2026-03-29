from aurum_voice.intelligence import (
    DomainIntelligenceService,
    IntelligenceItem,
    _classify_topics,
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


def test_classify_topics_detects_family_office_and_philanthropy() -> None:
    items = [
        IntelligenceItem(
            source="SourceA",
            title="Launch checklist for single family office formation",
            link="",
            published="",
            summary="Governance design and operating model guidance.",
        ),
        IntelligenceItem(
            source="SourceB",
            title="Philanthropy and donor-advised fund strategy",
            link="",
            published="",
            summary="Charitable planning for multigenerational families.",
        ),
    ]
    counts = _classify_topics(items)
    assert counts["family_office_creation"] >= 1
    assert counts["governance"] >= 1
    assert counts["philanthropy"] >= 1


def test_recommendation_payload_contains_plan() -> None:
    intelligence = DomainIntelligenceService()
    payload = intelligence.recommendations_payload()
    assert "plan" in payload
    assert "settings_patch" in payload["plan"]
    assert "priority_topics" in payload


def test_feedback_updates_acceptance_summary(tmp_path) -> None:
    feedback_path = tmp_path / "feedback.json"
    intelligence = DomainIntelligenceService(feedback_path=feedback_path)
    summary_before = intelligence.feedback_summary()
    assert summary_before["total_events"] == 0

    summary_after = intelligence.record_feedback(
        event_type="apply_ai_settings",
        accepted=True,
        topics=["governance"],
        metadata={"mode": "dialogue_advisory"},
    )
    assert summary_after["total_events"] == 1
    assert summary_after["topic_acceptance"]["governance"]["accepted"] >= 1
    assert feedback_path.exists()
