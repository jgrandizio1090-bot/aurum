from aurum_voice.intelligence import DomainIntelligenceService
from aurum_voice.web import _extract_segments, create_app


def test_index_route_renders() -> None:
    app = create_app(start_background_intelligence=False)
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Voice Studio" in response.data


def test_synthesize_requires_text() -> None:
    app = create_app(start_background_intelligence=False)
    client = app.test_client()
    response = client.post("/api/synthesize", json={"text": "   "})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Text is required."


def test_extract_segments_multi_voice_mode() -> None:
    text = "A: Hello there\nB: Welcome back\nUnlabeled line"
    segments = _extract_segments(text, "multi")
    assert segments == [("A", "Hello there"), ("B", "Welcome back"), ("A", "Unlabeled line")]


def test_intelligence_status_endpoint() -> None:
    intelligence = DomainIntelligenceService()
    app = create_app(intelligence_service=intelligence, start_background_intelligence=False)
    client = app.test_client()
    response = client.get("/api/intelligence/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert "revision" in payload
    assert "item_count" in payload
    assert "topic_counts" in payload
