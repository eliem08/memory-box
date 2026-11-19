"""Mem0 sync against a fake Mem0 server (request shapes from Mem0's v3 API reference; no network)."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from memory_box.__main__ import main
from memory_box.core import MemoryBox
from memory_box.mem0 import Mem0, SyncError, pull, push


class FakeMem0:
    """Holds memories per user; pages results 2 at a time to exercise pagination."""

    def __init__(self, existing=None):
        self.store = {"alice": list(existing or [])}
        self.calls = []

    def __call__(self, url, key, body):
        self.calls.append((url, key, body))
        if url.endswith("/v3/memories/add/"):
            assert body["infer"] is False and body["messages"][0]["role"] == "user"
            text = body["messages"][0]["content"]
            self.store.setdefault(body["user_id"], []).append({"id": str(len(self.calls)), "memory": text})
            return {"message": "ok", "results": [{"id": "x", "data": {"memory": text}, "event": "ADD"}]}
        page = int(url.split("page=")[1].split("&")[0])
        rows = self.store.get(body["filters"]["user_id"], [])
        chunk = rows[(page - 1) * 2 : page * 2]
        more = page * 2 < len(rows)
        return {"count": len(rows), "next": "more" if more else None, "previous": None, "results": chunk}


class Mem0Tests(unittest.TestCase):
    def box(self, *facts):
        b = MemoryBox()
        for text in facts:
            b.add(text, "chatgpt", "2026-11-01T10:00:00")
        return b

    def test_pull_merges_every_page(self):
        fake = FakeMem0(
            [
                {"memory": "Works at Acme Corp as a data engineer", "created_at": "2026-10-01T09:00:00Z"},
                {"memory": "Plays the cello on weekends", "created_at": "2026-10-02T09:00:00Z"},
                {"memory": "Prefers dark mode in every app", "created_at": "2026-10-03T09:00:00Z"},
            ]
        )
        b = self.box("Works at Acme Corp as a data engineer")
        n = pull(b, "alice", Mem0(key="k", post=fake))
        self.assertEqual(n, 2)  # the matching fact merged, two new ones added
        self.assertIn("mem0", next(f for f in b.facts if "Acme" in f.text).sources)
        self.assertEqual(sum(1 for c in fake.calls if "/v3/memories/?page=" in c[0]), 2)
        self.assertEqual(fake.calls[0][1], "k")

    def test_push_skips_what_mem0_has_and_sensitive_facts(self):
        fake = FakeMem0([{"memory": "Plays the cello on weekends"}])
        b = self.box("Plays the cello on weekends", "Prefers concise answers", "Has type 2 diabetes")
        sent = push(b, "alice", Mem0(key="k", post=fake))
        self.assertEqual(sent, 1)
        added = [c[2] for c in fake.calls if c[0].endswith("/add/")]
        self.assertEqual([a["messages"][0]["content"] for a in added], ["Prefers concise answers"])
        self.assertEqual(added[0]["metadata"]["category"], "style")
        self.assertEqual(push(b, "alice", Mem0(key="k", post=fake)), 0)  # nothing new the second time
        self.assertEqual(push(b, "alice", Mem0(key="k", post=fake), include_sensitive=True), 1)

    def test_refusals(self):
        with mock.patch.dict(os.environ, {"MEM0_API_KEY": ""}), self.assertRaisesRegex(SyncError, "MEM0_API_KEY"):
            Mem0()
        with self.assertRaisesRegex(SyncError, "https"):
            Mem0(key="k", base="http://mem0.local")
        with self.assertRaisesRegex(SyncError, "user-id"):
            pull(MemoryBox(), "bad user id", Mem0(key="k", post=FakeMem0()))

    def test_cli_sync_both_ways(self):
        fake = FakeMem0([{"memory": "Plays the cello on weekends"}])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "box.json")
            self.box("Prefers concise answers").save(path)
            out = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"MEM0_API_KEY": "k"}),
                mock.patch("memory_box.mem0._post", fake),
                contextlib.redirect_stdout(out),
            ):
                code = main(["sync", path, "--user-id", "alice"])
            self.assertEqual(code, 0, out.getvalue())
            self.assertIn("pulled from Mem0: 1 new fact(s)", out.getvalue())
            self.assertIn("pushed to Mem0: 1 fact(s)", out.getvalue())
            self.assertEqual(len(MemoryBox.load(path).facts), 2)


if __name__ == "__main__":
    unittest.main()
