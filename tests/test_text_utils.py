from aurum_voice.text_utils import TextChunker


def test_split_short_text_returns_single_chunk() -> None:
    chunker = TextChunker(max_chars=30)
    assert chunker.split("Hello world.") == ["Hello world."]


def test_split_long_text_respects_chunk_size() -> None:
    chunker = TextChunker(max_chars=15)
    text = "This is a somewhat longer sentence that needs chunking."
    chunks = chunker.split(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 15 for chunk in chunks)
    assert " ".join(chunks).startswith("This is")

