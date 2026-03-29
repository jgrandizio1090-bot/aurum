from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
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

_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "family_office_creation": (
        "family office",
        "single family office",
        "multi family office",
        "operating model",
        "launch",
        "formation",
        "setup",
    ),
    "governance": (
        "governance",
        "family constitution",
        "family council",
        "board",
        "fiduciary",
        "oversight",
        "succession",
        "decision rights",
    ),
    "family_advisory": (
        "family advisory",
        "next generation",
        "education",
        "advisor",
        "communication",
        "conflict",
        "values",
        "stewardship",
    ),
    "philanthropy": (
        "philanthropy",
        "charitable",
        "foundation",
        "donor-advised",
        "impact investing",
        "grantmaking",
        "giving",
        "nonprofit",
    ),
}

DEFAULT_SOURCES: tuple[tuple[str, str], ...] = (
    ("IRS Newsroom", "https://www.irs.gov/newsroom/rss"),
    ("SEC Press Releases", "https://www.sec.gov/news/pressreleases.rss"),
    ("U.S. Treasury News", "https://home.treasury.gov/news/press-releases/feed"),
    ("DOJ Press Releases", "https://www.justice.gov/feeds/press-release.xml"),
    ("Federal Reserve Press Releases", "https://www.federalreserve.gov/feeds/press_all.xml"),
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
    topic_counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class RecommendationPlan:
    mode: str
    summary: str
    rationale: list[str] = field(default_factory=list)
    settings_patch: dict[str, object] = field(default_factory=dict)
    suggested_script_template: str = ""
    priority_topics: list[str] = field(default_factory=list)


class DomainIntelligenceService:
    """Continuously refreshes domain news and builds reusable prompt context."""

    def __init__(
        self,
        *,
        refresh_interval_seconds: int = 900,
        request_timeout_seconds: float = 10.0,
        max_items: int = 18,
        sources: tuple[tuple[str, str], ...] = DEFAULT_SOURCES,
        feedback_path: str | Path | None = None,
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
        self._feedback_path = Path(feedback_path) if feedback_path else Path("/tmp/aurum_intelligence_feedback.json")
        self._feedback: dict[str, Any] = self._load_feedback()
        self._snapshot = IntelligenceSnapshot(
            generated_at=_utc_now_iso(),
            revision=0,
            items=[],
            keywords=[],
            source_status={},
            topic_counts={},
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
                topic_counts=dict(self._snapshot.topic_counts),
            )

    def status(self) -> dict[str, object]:
        snapshot = self.get_snapshot()
        plan = self.recommend_workflow_plan()
        return {
            "generated_at": snapshot.generated_at,
            "revision": snapshot.revision,
            "item_count": len(snapshot.items),
            "keywords": snapshot.keywords[:10],
            "source_status": snapshot.source_status,
            "topic_counts": snapshot.topic_counts,
            "priority_topics": plan.priority_topics,
            "recommended_mode": plan.mode,
            "feedback": self.feedback_summary(),
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
        if snapshot.topic_counts:
            ranked_topics = sorted(
                snapshot.topic_counts.items(),
                key=lambda pair: (-pair[1], pair[0]),
            )
            topic_line = ", ".join(
                f"{_topic_label(topic)} ({count})" for topic, count in ranked_topics if count > 0
            )
            if topic_line:
                lines.append("Topic coverage: " + topic_line)
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

    def recommend_workflow_plan(self) -> RecommendationPlan:
        snapshot = self.get_snapshot()
        topic_counts = snapshot.topic_counts or {topic: 0 for topic in _TOPIC_KEYWORDS}
        scored_topics = sorted(
            (
                (topic, self._topic_priority_score(topic, count))
                for topic, count in topic_counts.items()
            ),
            key=lambda pair: (-pair[1], pair[0]),
        )
        priority_topics = [topic for topic, _score in scored_topics[:3]]
        if not priority_topics:
            priority_topics = ["family_office_creation", "governance", "family_advisory"]

        dominant = priority_topics[0]
        if dominant in {"governance", "family_advisory"}:
            mode = "dialogue_advisory"
            template = (
                "A: Let's establish your family governance goals for this year.\n"
                "B: We need clearer decision rights and succession cadence.\n"
                "A: Great. We'll define a governance roadmap, then align advisory education steps."
            )
            summary = "Recommended dialogue mode for nuanced governance/advisory communication."
        elif dominant == "philanthropy":
            mode = "narrative_briefing"
            template = (
                "A: This briefing outlines philanthropic strategy priorities.\n"
                "A: We align mission, grantmaking cadence, and measurable impact goals.\n"
                "A: Next, we map governance and tax-aware execution steps."
            )
            summary = "Recommended narrative mode for mission-driven philanthropy briefings."
        else:
            mode = "structured_overview"
            template = (
                "A: We are launching a modern family office operating model.\n"
                "A: First, define legal and governance foundations.\n"
                "A: Then align advisory services, risk controls, and family mission outcomes."
            )
            summary = "Recommended structured mode for family office design and implementation."

        settings_patch: dict[str, object] = {
            "script_mode": "multi" if mode == "dialogue_advisory" else "single",
            "quality": "expressive" if mode != "structured_overview" else "balanced",
            "crossfade_ms": 28 if mode == "dialogue_advisory" else 24,
            "stability": 0.58 if mode == "dialogue_advisory" else 0.64,
            "similarity_boost": 0.78,
            "style": 0.22 if mode in {"dialogue_advisory", "narrative_briefing"} else 0.16,
            "speaker_boost": True,
            "use_intelligence": True,
            "apply_intelligence_context": False,
            "mastering": {
                "enabled": True,
                "normalize": True,
                "fade_ms": 14,
                "peak_target": 0.91,
            },
        }
        rationale = [
            f"Dominant intelligence topic: {_topic_label(dominant)}",
            "Selected settings favor clarity and professionalism for advisor-client communication.",
            "Mastering defaults keep output polished while preserving intelligibility.",
        ]
        feedback = self.feedback_summary()
        if feedback["total_events"] > 0:
            rationale.append(
                f"Learned from {feedback['total_events']} user feedback events to prioritize higher-acceptance topics."
            )
        return RecommendationPlan(
            mode=mode,
            summary=summary,
            rationale=rationale,
            settings_patch=settings_patch,
            suggested_script_template=template,
            priority_topics=priority_topics,
        )

    def recommendations_payload(self) -> dict[str, object]:
        snapshot = self.get_snapshot()
        plan = self.recommend_workflow_plan()
        return {
            "generated_at": snapshot.generated_at,
            "revision": snapshot.revision,
            "topic_counts": snapshot.topic_counts,
            "priority_topics": plan.priority_topics,
            "plan": asdict(plan),
            "feedback": self.feedback_summary(),
        }

    def record_feedback(
        self,
        *,
        event_type: str,
        accepted: bool = True,
        topics: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        normalized_event = (event_type or "unknown").strip().lower() or "unknown"
        normalized_topics = [topic for topic in (topics or []) if topic in _TOPIC_KEYWORDS]
        with self._lock:
            self._feedback["total_events"] = int(self._feedback.get("total_events", 0)) + 1
            event_counts = self._feedback.setdefault("event_counts", {})
            event_counts[normalized_event] = int(event_counts.get(normalized_event, 0)) + 1
            topic_feedback = self._feedback.setdefault("topic_acceptance", {})
            for topic in normalized_topics:
                bucket = topic_feedback.setdefault(topic, {"accepted": 0, "rejected": 0})
                key = "accepted" if accepted else "rejected"
                bucket[key] = int(bucket.get(key, 0)) + 1
            # Keep a lightweight rolling trace for diagnostics.
            recent = self._feedback.setdefault("recent_events", [])
            recent.append(
                {
                    "at": _utc_now_iso(),
                    "event_type": normalized_event,
                    "accepted": bool(accepted),
                    "topics": normalized_topics,
                    "metadata": metadata or {},
                }
            )
            self._feedback["recent_events"] = recent[-40:]
            self._persist_feedback_locked()
        return self.feedback_summary()

    def feedback_summary(self) -> dict[str, object]:
        with self._lock:
            total_events = int(self._feedback.get("total_events", 0))
            event_counts = {
                key: int(value) for key, value in dict(self._feedback.get("event_counts", {})).items()
            }
            topic_acceptance: dict[str, dict[str, int]] = {}
            for topic in _TOPIC_KEYWORDS:
                bucket = dict(self._feedback.get("topic_acceptance", {}).get(topic, {}))
                topic_acceptance[topic] = {
                    "accepted": int(bucket.get("accepted", 0)),
                    "rejected": int(bucket.get("rejected", 0)),
                }

        acceptance_rate_by_topic: dict[str, float] = {}
        for topic, bucket in topic_acceptance.items():
            total = bucket["accepted"] + bucket["rejected"]
            acceptance_rate_by_topic[topic] = (
                round(bucket["accepted"] / total, 3) if total > 0 else 0.0
            )

        return {
            "total_events": total_events,
            "event_counts": event_counts,
            "topic_acceptance": topic_acceptance,
            "acceptance_rate_by_topic": acceptance_rate_by_topic,
        }

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
        topic_counts = _classify_topics(deduped)

        with self._lock:
            self._snapshot = IntelligenceSnapshot(
                generated_at=_utc_now_iso(),
                revision=self._snapshot.revision + 1,
                items=deduped,
                keywords=keywords,
                source_status=source_status,
                topic_counts=topic_counts,
            )

    def _topic_priority_score(self, topic: str, signal_count: int) -> float:
        base = float(signal_count)
        bucket = self._feedback.get("topic_acceptance", {}).get(topic, {})
        accepted = int(bucket.get("accepted", 0))
        rejected = int(bucket.get("rejected", 0))
        total = accepted + rejected
        if total <= 0:
            return base
        acceptance_delta = (accepted / total) - 0.5
        confidence = min(1.0, total / 8.0)
        return base + (acceptance_delta * confidence * 4.0)

    def _load_feedback(self) -> dict[str, Any]:
        try:
            if self._feedback_path.exists():
                raw = json.loads(self._feedback_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return self._normalize_feedback(raw)
        except Exception:
            pass
        return self._default_feedback()

    def _persist_feedback_locked(self) -> None:
        try:
            self._feedback_path.parent.mkdir(parents=True, exist_ok=True)
            self._feedback_path.write_text(
                json.dumps(self._feedback, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception:
            # Never let persistence failures break the core app flow.
            return

    def _default_feedback(self) -> dict[str, Any]:
        return {
            "total_events": 0,
            "event_counts": {},
            "topic_acceptance": {topic: {"accepted": 0, "rejected": 0} for topic in _TOPIC_KEYWORDS},
            "recent_events": [],
        }

    def _normalize_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._default_feedback()
        normalized["total_events"] = int(payload.get("total_events", 0))
        event_counts = payload.get("event_counts", {})
        if isinstance(event_counts, dict):
            normalized["event_counts"] = {str(k): int(v) for k, v in event_counts.items()}
        topic_acceptance = payload.get("topic_acceptance", {})
        if isinstance(topic_acceptance, dict):
            for topic in _TOPIC_KEYWORDS:
                bucket = topic_acceptance.get(topic, {})
                if isinstance(bucket, dict):
                    normalized["topic_acceptance"][topic] = {
                        "accepted": int(bucket.get("accepted", 0)),
                        "rejected": int(bucket.get("rejected", 0)),
                    }
        recent_events = payload.get("recent_events", [])
        if isinstance(recent_events, list):
            normalized["recent_events"] = recent_events[-40:]
        return normalized


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


def _classify_topics(items: list[IntelligenceItem]) -> dict[str, int]:
    counts = {topic: 0 for topic in _TOPIC_KEYWORDS}
    for item in items:
        text = f"{item.title} {item.summary}".lower()
        for topic, patterns in _TOPIC_KEYWORDS.items():
            if any(pattern in text for pattern in patterns):
                counts[topic] += 1
    return counts


def _topic_label(topic: str) -> str:
    mapping = {
        "family_office_creation": "Family Office Creation",
        "governance": "Governance",
        "family_advisory": "Family Advisory",
        "philanthropy": "Philanthropy",
    }
    return mapping.get(topic, topic)


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
