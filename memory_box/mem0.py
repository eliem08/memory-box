"""Two-way sync with Mem0's hosted API (v3), using only the standard library.

pull: every memory Mem0 holds for a user comes into the box (merged and deduplicated like any import).
push: the box's facts go to Mem0 for that user, stored verbatim (`infer: false`, so Mem0's model does not
      rewrite them), skipping facts Mem0 already has and resolving conflicts newest-first as `export` does.
      Sensitive categories (health, location, people) stay out unless you pass --include-sensitive.

Key: MEM0_API_KEY. Base URL: MEM0_API_URL (default https://api.mem0.ai; a self-hosted Mem0 server exposes a
different API and is not supported here).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .core import MemoryBox, _similar, looks_like_instruction

USER_RE = re.compile(r"^[\w.@+-]{1,128}$")
PAGE_SIZE, MAX_PAGES = 200, 50


class SyncError(ValueError):
    pass


def _post(url: str, key: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Token {key}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        with e:
            detail = e.read()[:200].decode("utf-8", "replace")
        if e.code == 401:
            raise SyncError("Mem0 rejected the API key (MEM0_API_KEY)") from None
        raise SyncError(f"Mem0 answered {e.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as e:
        raise SyncError(f"could not reach Mem0: {e}") from None


class Mem0:
    def __init__(self, key: str | None = None, base: str | None = None, post=None):
        self.key = key if key is not None else os.environ.get("MEM0_API_KEY", "")
        self.base = (base or os.environ.get("MEM0_API_URL") or "https://api.mem0.ai").rstrip("/")
        if not self.key:
            raise SyncError("set MEM0_API_KEY to sync with Mem0")
        if not self.base.startswith("https://"):
            raise SyncError("MEM0_API_URL must be https://")
        self.post = post or _post

    def memories(self, user_id: str) -> list[dict]:
        out = []
        for page in range(1, MAX_PAGES + 1):
            res = self.post(
                f"{self.base}/v3/memories/?page={page}&page_size={PAGE_SIZE}",
                self.key,
                {"filters": {"user_id": user_id}},
            )
            rows = res.get("results") if isinstance(res, dict) else res
            out += [r for r in rows or [] if isinstance(r, dict) and isinstance(r.get("memory"), str)]
            if not isinstance(res, dict) or not res.get("next"):
                break
        return out

    def add(self, user_id: str, text: str, metadata: dict) -> dict:
        body = {
            "user_id": user_id,
            "messages": [{"role": "user", "content": text}],
            "infer": False,
            "metadata": metadata,
        }
        return self.post(f"{self.base}/v3/memories/add/", self.key, body)


def _check_user(user_id: str):
    if not USER_RE.match(user_id or ""):
        raise SyncError("--user-id must be 1-128 letters, digits or . _ @ + -")


def pull(box: MemoryBox, user_id: str, client: Mem0) -> int:
    _check_user(user_id)
    before = len(box.facts)
    for m in client.memories(user_id):
        created = str(m.get("created_at") or "")[:19] or None
        box.add(m["memory"].strip(), "mem0", created)
    return len(box.facts) - before


def plan_push(box: MemoryBox, existing: list[str], include_sensitive: bool = False) -> list:
    """Facts to send: newest of each conflict, no instructions, not already in Mem0, sensitive only if asked."""
    stale = {id(f) for _, group in box.conflicts() for f in sorted(group, key=lambda f: f.created)[:-1]}
    return [
        f
        for f in box.facts
        if id(f) not in stale
        and (include_sensitive or not f.sensitive)
        and not looks_like_instruction(f.text)
        and not any(_similar(f.text, e) for e in existing)
    ]


def push(box: MemoryBox, user_id: str, client: Mem0, include_sensitive: bool = False) -> int:
    _check_user(user_id)
    existing = [m["memory"] for m in client.memories(user_id)]
    todo = plan_push(box, existing, include_sensitive)
    for f in todo:
        client.add(user_id, f.text, {"category": f.category, "memory_box_id": f.id, "sources": ",".join(f.sources)})
    return len(todo)
