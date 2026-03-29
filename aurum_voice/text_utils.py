from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TextChunker:
    """Breaks text into sentence-aware chunks for better TTS pacing."""

    max_chars: int = 350

    def split(self, text: str) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []
        if len(normalized) <= self.max_chars:
            return [normalized]

        chunks: list[str] = []
        sentence = []
        current_len = 0

        for token in normalized.split(" "):
            token_len = len(token) + (1 if sentence else 0)
            if current_len + token_len <= self.max_chars:
                sentence.append(token)
                current_len += token_len
                continue

            if sentence:
                chunks.append(" ".join(sentence))
                sentence = [token]
                current_len = len(token)
            else:
                # Extremely long token fallback.
                chunks.extend(self._hard_wrap(token))
                sentence = []
                current_len = 0

        if sentence:
            chunks.append(" ".join(sentence))
        return chunks

    def _hard_wrap(self, token: str) -> list[str]:
        return [token[i : i + self.max_chars] for i in range(0, len(token), self.max_chars)]
