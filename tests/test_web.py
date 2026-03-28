from aurum_voice.web import create_app


def test_index_route_renders() -> None:
    app = create_app()
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Voice Studio" in response.data


def test_synthesize_requires_text() -> None:
    app = create_app()
    client = app.test_client()
    response = client.post("/api/synthesize", json={"text": "   "})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Text is required."
