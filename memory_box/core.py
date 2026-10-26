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

__all__ = ["Fact", "MemoryBox", "parse_text", "categorize", "looks_like_instruction"]

# A memory is a fact about the user, never an order to the next agent. Anything shaped like a prompt injection
# is kept in the file (so the user can see and delete it) but never exported into another agent's context.
INJECTION_RE = re.compile(
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|prompts?|rules|guidelines|system)\b"
    r"|\bsystem prompt\b|\byou are now\b|\bnew instructions\b|\bact as\b.{0,30}\b(admin|developer|root)\b"
    r"|\b(reveal|print|send|exfiltrate)\b.{0,40}\b(password|api key|secret|token|credentials?)\b",
    re.I | re.S,
)


def looks_like_instruction(text: str) -> bool:
    return bool(INJECTION_RE.search(text))


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


TEXT_KEYS = ("text", "content", "memory", "value", "fact")  # ours/OpenAI, Mem0, Letta blocks, generic
LIST_KEYS = ("memories", "facts", "results", "blocks", "items")


def _item_text(item) -> str:
    if isinstance(item, str):
        return item
    return next((str(item[k]) for k in TEXT_KEYS if item.get(k)), "")


def _parse_csv(raw: str) -> list[str] | None:
    """A spreadsheet export with a memory/text/fact column; None when the text is not such a CSV."""
    import csv
    import io

    first = raw.lstrip("﻿").split("\n", 1)[0].lower()
    if "," not in first or not any(k in [c.strip() for c in first.split(",")] for k in TEXT_KEYS):
        return None
    rows = csv.DictReader(io.StringIO(raw.lstrip("﻿")))
    col = next(c for c in rows.fieldnames or [] if c.strip().lower() in TEXT_KEYS)
    return [r[col].strip() for r in rows if (r.get(col) or "").strip()]


def parse_text(raw: str) -> list[str]:
    """Extract one fact per item from JSON (ours, Mem0, Letta), JSONL, CSV, or plain-text/markdown dumps."""
    if raw.lstrip().startswith(("[", "{")):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                items = data
            else:
                items = next((data[k] for k in LIST_KEYS if isinstance(data.get(k), list)), [])
            if not isinstance(items, list) or not all(isinstance(i, (str, dict)) for i in items):
                raise ValueError("memory export must be a list of strings or {text|content|memory} objects")
            return [t for t in (_item_text(i) for i in items) if t]
        except json.JSONDecodeError:
            pass
    from_csv = _parse_csv(raw)
    if from_csv is not None:
        return from_csv
    facts = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                facts.append(_item_text(json.loads(line)))
                continue
            except json.JSONDecodeError:
                pass
        line = re.sub(r"^([-*+•]|\d+[.)])\s+", "", line)
        if not line or line.startswith("#") or len(line) < 4:
            continue
        facts.append(line)
    return [f for f in facts if f]


# Where each assistant keeps what it knows about you, and how much it holds
TARGETS = {
    # ChatGPT > Settings > Personalization > Custom instructions: "What would you like ChatGPT to know about you?"
    "chatgpt": {"chars": 1500, "header": "", "line": "- {text}."},
    # Claude project instructions or a CLAUDE.md "About me" section
    "claude": {"chars": None, "header": "## About me", "line": "- {text} ({category})"},
    # Gemini > Saved info: one entry per line, each pasted separately
    "gemini": {"chars": None, "header": "", "line": "{text}."},
}


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
        with open(path, encoding="utf-8-sig") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or not isinstance(doc.get("facts"), list):
            raise ValueError(f"{path}: not a memory-box file (expected an object with a facts list)")
        body = json.dumps(doc["facts"], sort_keys=True).encode()
        if key and not hmac.compare_digest(doc.get("signature", ""), hmac.new(key, body, hashlib.sha256).hexdigest()):
            raise ValueError("signature mismatch - memory file was modified")
        fields = set(Fact.__dataclass_fields__)
        for f in doc["facts"]:
            if not isinstance(f, dict) or not {"text", "category", "sources", "created"} <= set(f) <= fields:
                raise ValueError(f"{path}: malformed fact {f!r:.80}")
        return cls([Fact(**f) for f in doc["facts"]])

    def save(self, path, key: bytes | None = None):
        facts = [asdict(f) for f in self.facts]
        body = json.dumps(facts, sort_keys=True).encode()
        doc = {"format": self.VERSION, "facts": facts}
        if key:
            doc["signature"] = hmac.new(key, body, hashlib.sha256).hexdigest()
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:  # write-then-rename: a crash never leaves half a file
            json.dump(doc, fh, indent=2)
        os.replace(tmp, path)

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
            if (not categories or f.category in categories)
            and (include_sensitive or not f.sensitive)
            and (fmt == "json" or not looks_like_instruction(f.text))
        ]
        facts.sort(key=lambda f: (-f.confidence, f.created), reverse=False)
        if fmt == "json":
            return json.dumps([asdict(f) for f in facts], indent=2)
        if fmt == "mem0" or fmt in TARGETS:
            # an assistant cannot hold "lives in Paris" and "lives in Lyon" at once: the newest fact wins
            stale = {id(f) for _, group in self.conflicts() for f in sorted(group, key=lambda f: f.created)[:-1]}
            facts = [f for f in facts if id(f) not in stale]
        if fmt == "mem0":  # ready for Mem0's add/import: one memory per item, category kept as metadata
            return json.dumps(
                {"memories": [{"memory": f.text, "metadata": {"category": f.category}} for f in facts]}, indent=2
            )
        if fmt in TARGETS:
            return self._for_assistant(fmt, facts, budget_tokens)
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

    @staticmethod
    def _for_assistant(fmt: str, facts: list[Fact], budget_tokens: int | None) -> str:
        """Text shaped for one assistant's memory box, cut to its real size limit, best facts first."""
        spec = TARGETS[fmt]
        limit = min(spec["chars"] or 10**9, budget_tokens * 4 if budget_tokens else 10**9)
        out = [spec["header"]] if spec["header"] else []
        used = sum(len(x) + 1 for x in out)
        for f in facts:
            line = spec["line"].format(text=f.text.rstrip("."), category=f.category)
            if used + len(line) + 1 > limit:
                continue
            out.append(line)
            used += len(line) + 1
        return "\n".join(out)
