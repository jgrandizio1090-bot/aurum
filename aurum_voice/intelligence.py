from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable
from xml.etree import ElementTree as ET

import httpx

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{3,}")
_TAG_RE = re.compile(r"<[^>]+>")

_STOPWORDS = {
    "about",
    "after",
    "also",
    "analysis",
    "announces",
    "assets",
    "because",
    "before",
    "being",
    "between",
    "business",
    "client",
    "compliance",
    "could",
    "finance",
    "financial",
    "guidance",
    "investment",
    "investors",
    "management",
    "market",
    "money",
    "planning",
    "press",
    "release",
    "releases",
    "report",
    "reports",
    "should",
    "their",
    "there",
    "these",
    "those",
    "today",
    "update",
    "wealth",
    "while",
    "would",
}

DEFAULT_SOURCES: tuple[tuple[str, str], ...] = (
    ("IRS Newsroom", "https://www.irs.gov/newsroom/rss"),
    ("SEC Press Releases", "https://www.sec.gov/news/pressreleases.rss"),
    ("U.S. Treasury News", "https://home.treasury.gov/news/press-releases/feed"),
)


@dataclass(slots=True)
class IntelligenceItem:
    source: str
    title: str
    link: str
    published: str
    summary: str


@dataclass(slots=True)
class IntelligenceSnapshot:
    generated_at: str
    revision: int
    items: list[IntelligenceItem] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    source_status: dict[str, str] = field(default_factory=dict)


class DomainIntelligenceService:
    """Continuously refreshes domain news and builds reusable prompt context."""

    def __init__(
        self,
        *,
        refresh_interval_seconds: int = 900,
        request_timeout_seconds: float = 10.0,
        max_items: int = 18,
        sources: tuple[tuple[str, str], ...] = DEFAULT_SOURCES,
    ) -> None:
        self.refresh_interval_seconds = max(60, refresh_interval_seconds)
        self.max_items = max(3, max_items)
        self.sources = sources
        self._min_refresh_gap_seconds = 20

        self._client = httpx.Client(timeout=request_timeout_seconds, follow_redirects=True)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_refresh_monotonic = 0.0
        self._snapshot = IntelligenceSnapshot(
            generated_at=_utc_now_iso(),
            revision=0,
            items=[],
            keywords=[],
            source_status={},
        )

    def start_background_refresh(self) -> None:
        self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="aurum-intelligence", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._client.close()

    def refresh_now(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and (now - self._last_refresh_monotonic) < self._min_refresh_gap_seconds:
            return False
        self._last_refresh_monotonic = now
        self._refresh_once()
        return True

    def get_snapshot(self) -> IntelligenceSnapshot:
        with self._lock:
            return IntelligenceSnapshot(
                generated_at=self._snapshot.generated_at,
                revision=self._snapshot.revision,
                items=list(self._snapshot.items),
                keywords=list(self._snapshot.keywords),
                source_status=dict(self._snapshot.source_status),
            )

    def status(self) -> dict[str, object]:
        snapshot = self.get_snapshot()
        return {
            "generated_at": snapshot.generated_at,
            "revision": snapshot.revision,
            "item_count": len(snapshot.items),
            "keywords": snapshot.keywords[:10],
            "source_status": snapshot.source_status,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "healthy": len(snapshot.items) > 0,
        }

    def get_context_for_prompt(self, *, max_chars: int = 800) -> str:
        return self.build_context(max_chars=max_chars)

    def build_context(self, *, max_chars: int = 800) -> str:
        snapshot = self.get_snapshot()
        if not snapshot.items:
            return "No fresh policy context is available yet."

        max_chars = max(180, min(2500, max_chars))
        lines: list[str] = []
        if snapshot.keywords:
            lines.append("Priority signals: " + ", ".join(snapshot.keywords[:8]))
        for item in snapshot.items[:6]:
            bullet = f"- {item.title}"
            if item.published:
                bullet += f" ({item.published})"
            if item.summary:
                bullet += f": {item.summary}"
            lines.append(bullet)

        out: list[str] = []
        total = 0
        for line in lines:
            addition = f"{line}\n"
            if total + len(addition) > max_chars:
                break
            out.append(addition)
            total += len(addition)
        return "".join(out).strip()

    def enhance_prompt(self, prompt: str, *, max_chars: int = 800) -> str:
        base = prompt.strip()
        if not base:
            return ""
        context = self.build_context(max_chars=max_chars)
        if context.startswith("No fresh policy context"):
            return base
        return (
            f"{base}\n\n"
            "Incorporate the latest wealth-management and tax-policy context below. "
            "Keep guidance compliant, practical, and client-friendly:\n"
            f"{context}"
        )

    def _run(self) -> None:
        self.refresh_now(force=True)
        while not self._stop_event.wait(self.refresh_interval_seconds):
            self.refresh_now(force=True)

    def _refresh_once(self) -> None:
        all_items: list[IntelligenceItem] = []
        source_status: dict[str, str] = {}

        for source_name, source_url in self.sources:
            try:
                response = self._client.get(source_url)
                response.raise_for_status()
                parsed = _parse_feed(source_name, response.text)
                source_status[source_name] = f"ok ({len(parsed)} items)"
                all_items.extend(parsed[:6])
            except Exception as exc:  # noqa: BLE001 - keep service resilient
                source_status[source_name] = f"error ({exc.__class__.__name__})"

        deduped = _dedupe_items(all_items)[: self.max_items]
        keywords = _extract_keywords(deduped)

        with self._lock:
            self._snapshot = IntelligenceSnapshot(
                generated_at=_utc_now_iso(),
                revision=self._snapshot.revision + 1,
                items=deduped,
                keywords=keywords,
                source_status=source_status,
            )


def _dedupe_items(items: Iterable[IntelligenceItem]) -> list[IntelligenceItem]:
    seen: set[tuple[str, str]] = set()
    output: list[IntelligenceItem] = []
    for item in items:
        key = (item.source, item.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _parse_feed(source_name: str, xml_text: str) -> list[IntelligenceItem]:
    root = ET.fromstring(xml_text)
    if root.tag.lower().endswith("feed"):  # Atom
        return _parse_atom(source_name, root)
    return _parse_rss(source_name, root)


def _parse_rss(source_name: str, root: ET.Element) -> list[IntelligenceItem]:
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[IntelligenceItem] = []
    for node in channel.findall("item"):
        title = _clean_text(_node_text(node, "title"))
        if not title:
            continue
        items.append(
            IntelligenceItem(
                source=source_name,
                title=title,
                link=_clean_text(_node_text(node, "link")),
                published=_clean_text(_node_text(node, "pubDate")),
                summary=_clean_text(_node_text(node, "description"))[:280],
            )
        )
    return items


def _parse_atom(source_name: str, root: ET.Element) -> list[IntelligenceItem]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    items: list[IntelligenceItem] = []
    for entry in entries:
        title = _clean_text(_node_text(entry, "atom:title", ns))
        if not title:
            continue
        link_node = entry.find("atom:link", ns)
        link = ""
        if link_node is not None:
            link = _clean_text(link_node.attrib.get("href", ""))
        items.append(
            IntelligenceItem(
                source=source_name,
                title=title,
                link=link,
                published=_clean_text(_node_text(entry, "atom:updated", ns)),
                summary=_clean_text(_node_text(entry, "atom:summary", ns))[:280],
            )
        )
    return items


def _node_text(node: ET.Element, path: str, ns: dict[str, str] | None = None) -> str:
    child = node.find(path, ns or {})
    if child is None or child.text is None:
        return ""
    return child.text


def _clean_text(value: str) -> str:
    stripped = _TAG_RE.sub(" ", value or "")
    return " ".join(stripped.split())


def _extract_keywords(items: list[IntelligenceItem], *, max_keywords: int = 12) -> list[str]:
    counts: dict[str, int] = {}
    for item in items:
        text = f"{item.title} {item.summary}".lower()
        for token in _WORD_RE.findall(text):
            if token in _STOPWORDS:
                continue
            counts[token] = counts.get(token, 0) + 1

    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [word for word, _ in ranked[:max_keywords]]


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
