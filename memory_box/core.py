"""Portable memory format: import, merge, conflict detection and export."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

__all__ = ["Fact", "MemoryBox", "parse_text", "categorize"]

CATEGORY_HINTS = {
    "health": ["allergic", "allergy", "diet", "vegetarian", "vegan", "medication", "condition", "diagnosed", "gluten"],
    "location": ["lives in", "based in", "moved to", "from ", "timezone", "located in"],
    "work": ["works at", "work at", "job", "role", "engineer", "manager", "company", "employer", "startup"],
    "projects": ["project", "building", "repo", "codebase", "launching", "working on"],
    "people": ["wife", "husband", "partner", "son", "daughter", "kids", "mother", "father", "friend", "dog", "cat"],
    "style": ["prefers concise", "tone", "format", "bullet", "short answers", "explain", "writing style"],
    "preferences": ["prefers", "likes", "loves", "favorite", "favourite", "hates", "dislikes", "enjoys"],
    "identity": ["name is", "called", "years old", "pronouns", "born"],
}
SENSITIVE = {"health", "location", "people"}
# Single-valued attributes: (regex capturing the value) -> attribute name
SINGLE_VALUED = {
    r"\b(?i:lives|based|located) in ([A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)": "home_location",
    r"\b(?i:works?) (?:at|for) ([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*)": "employer",
    r"\b(?i:name) is ([A-Z][\w-]+)": "name",
    r"\b(\d{1,3}) years old": "age",
}


def categorize(text: str) -> str:
    low = text.lower()
    for cat, hints in CATEGORY_HINTS.items():
        if any(h in low for h in hints):
            return cat
    return "general"


@dataclass
class Fact:
    text: str
    category: str
    sources: list
    created: str
    confidence: float = 0.8
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def sensitive(self) -> bool:
        return self.category in SENSITIVE


def parse_text(raw: str) -> list[str]:
    """Extract one fact per bullet / line from plain-text or markdown memory dumps."""
    if raw.lstrip().startswith(("[", "{")):
        try:
            data = json.loads(raw)
            items = data if isinstance(data, list) else data.get("memories", data.get("facts", []))
            return [i if isinstance(i, str) else i.get("text") or i.get("content", "") for i in items]
        except json.JSONDecodeError:
            pass
    facts = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                o = json.loads(line)
                facts.append(o.get("text") or o.get("content", ""))
                continue
            except json.JSONDecodeError:
                pass
        line = re.sub(r"^([-*+•]|\d+[.)])\s+", "", line)
        if not line or line.startswith("#") or len(line) < 4:
            continue
        facts.append(line)
    return [f for f in facts if f]


def _norm_tokens(text):
    stop = {"the", "a", "an", "is", "are", "user", "they", "i", "my", "to", "and", "of", "in", "s"}
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in stop}


def _similar(a, b, threshold=0.7):
    ta, tb = _norm_tokens(a), _norm_tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= threshold


class MemoryBox:
    VERSION = "pmf/0.1"

    def __init__(self, facts: list[Fact] | None = None):
        self.facts = facts or []

    # io ------------------------------------------------------------------
    @classmethod
    def load(cls, path, key: bytes | None = None):
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        body = json.dumps(doc["facts"], sort_keys=True).encode()
        if key and not hmac.compare_digest(doc.get("signature", ""), hmac.new(key, body, hashlib.sha256).hexdigest()):
            raise ValueError("signature mismatch - memory file was modified")
        return cls([Fact(**f) for f in doc["facts"]])

    def save(self, path, key: bytes | None = None):
        facts = [asdict(f) for f in self.facts]
        body = json.dumps(facts, sort_keys=True).encode()
        doc = {"format": self.VERSION, "facts": facts}
        if key:
            doc["signature"] = hmac.new(key, body, hashlib.sha256).hexdigest()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)

    # merge ---------------------------------------------------------------
    def add(self, text: str, source: str, created: str | None = None) -> Fact:
        created = created or datetime.now(timezone.utc).isoformat(timespec="seconds")
        for f in self.facts:
            if _similar(f.text, text):
                if source not in f.sources:
                    f.sources.append(source)
                    f.confidence = min(1.0, f.confidence + 0.1)
                if created > f.created:
                    f.text, f.created = text, created
                return f
        fact = Fact(text, categorize(text), [source], created)
        self.facts.append(fact)
        return fact

    def import_text(self, raw: str, source: str, created: str | None = None) -> int:
        before = len(self.facts)
        for t in parse_text(raw):
            self.add(t, source, created)
        return len(self.facts) - before

    def conflicts(self) -> list[tuple[str, list[Fact]]]:
        values: dict[str, dict[str, list[Fact]]] = {}
        for f in self.facts:
            for rx, attr in SINGLE_VALUED.items():
                m = re.search(rx, f.text)
                if m:
                    values.setdefault(attr, {}).setdefault(m.group(1).strip().rstrip(".").lower(), []).append(f)
        return [(attr, [fs[0] for fs in vals.values()]) for attr, vals in values.items() if len(vals) > 1]

    # export --------------------------------------------------------------
    def export(
        self,
        fmt: str = "markdown",
        budget_tokens: int | None = None,
        categories: list[str] | None = None,
        include_sensitive: bool = True,
    ) -> str:
        facts = [
            f
            for f in self.facts
            if (not categories or f.category in categories) and (include_sensitive or not f.sensitive)
        ]
        facts.sort(key=lambda f: (-f.confidence, f.created), reverse=False)
        if fmt == "json":
            return json.dumps([asdict(f) for f in facts], indent=2)
        lines, used = [], 0
        header = "Things you know about the user (portable memory):" if fmt == "prompt" else "# Memory"
        used += len(header) // 4
        by_cat: dict[str, list[str]] = {}
        for f in facts:
            cost = len(f.text) // 4 + 2
            if budget_tokens and used + cost > budget_tokens:
                continue
            used += cost
            by_cat.setdefault(f.category, []).append(f.text)
        lines.append(header)
        for cat, items in by_cat.items():
            if fmt == "markdown":
                lines.append(f"\n## {cat}")
            for t in items:
                lines.append(f"- {t}" if fmt == "markdown" else f"- [{cat}] {t}")
        return "\n".join(lines)
