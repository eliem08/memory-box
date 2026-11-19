import argparse
import csv
import os
import sys

from .core import MemoryBox
from .mem0 import Mem0, plan_push, pull, push


def _key():
    k = os.environ.get("MEMORY_BOX_KEY")
    return k.encode() if k else None


def build_parser():
    ap = argparse.ArgumentParser(prog="memory-box")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import")
    i.add_argument("file")
    i.add_argument("--source", required=True)
    i.add_argument("-o", "--out", default="memory-box.json")
    c = sub.add_parser("conflicts")
    c.add_argument("box")
    e = sub.add_parser("export")
    e.add_argument("box")
    e.add_argument(
        "--format", choices=["markdown", "prompt", "json", "chatgpt", "claude", "gemini", "mem0"], default="markdown"
    )
    e.add_argument("--budget", type=int)
    e.add_argument("--categories", nargs="*")
    e.add_argument("--no-sensitive", action="store_true")
    s = sub.add_parser("sync", help="pull from and push to Mem0 for one user (MEM0_API_KEY)")
    s.add_argument("box")
    s.add_argument("--user-id", required=True, help="the Mem0 user the memories belong to")
    s.add_argument("--direction", choices=["pull", "push", "both"], default="both")
    s.add_argument("--include-sensitive", action="store_true", help="also push health, location and people facts")
    s.add_argument("--dry-run", action="store_true", help="show what a push would send; no network")
    return ap


def _run(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)

    if a.cmd == "import":
        box = MemoryBox.load(a.out, _key())
        with open(a.file, encoding="utf-8-sig") as fh:
            added = box.import_text(fh.read(), a.source)
        box.save(a.out, _key())
        print(f"imported from {a.source}: {added} new facts, {len(box.facts)} total -> {a.out}")
        return 0
    box = MemoryBox.load(a.box, _key())
    if a.cmd == "sync":
        if a.dry_run:
            todo = plan_push(box, [], a.include_sensitive)
            for f in todo:
                print(f"would push [{f.category}] {f.text}")
            held = sum(1 for f in box.facts if f.sensitive) if not a.include_sensitive else 0
            print(
                f"{len(todo)} fact(s) would go to Mem0 for {a.user_id} (before skipping ones it already has); "
                f"{held} sensitive kept back"
            )
            return 0
        client = Mem0()
        if a.direction in ("pull", "both"):
            n = pull(box, a.user_id, client)
            box.save(a.box, _key())
            print(f"pulled from Mem0: {n} new fact(s); {len(box.facts)} in the box")
        if a.direction in ("push", "both"):
            print(f"pushed to Mem0: {push(box, a.user_id, client, a.include_sensitive)} fact(s) for {a.user_id}")
        return 0
    if a.cmd == "conflicts":
        found = box.conflicts()
        for attr, facts in found:
            print(f"{attr}:")
            for f in facts:
                print(f"  - {f.text}  ({', '.join(f.sources)}, {f.created})")
        if not found:
            print("no conflicts")
            return 1  # nothing found: the domain answer for a clean box
        return 0
    print(box.export(a.format, a.budget, a.categories, not a.no_sensitive))
    return 0


def main(argv=None):
    """Run the CLI; a bad input file or argument exits 2 with a one-line error instead of a traceback.

    Set AGENT_ECONOMY_DEBUG=1 to see the full traceback.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        return _run(argv)
    except (OSError, ValueError, KeyError, csv.Error) as e:
        if os.environ.get("AGENT_ECONOMY_DEBUG"):
            raise
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"error: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
