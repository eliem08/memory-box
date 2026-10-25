<!-- sell-kit:start -->
# Memory Box

[![CI](https://github.com/eliem08/memory-box/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/memory-box/actions/workflows/ci.yml)

> **Take what your AI knows about you to any other AI.**

**Who it's for:** Heavy AI users switching between assistants.

**The problem:** Every assistant keeps its own memory of you, so switching tools means starting from zero or pasting in junk.

**What you get:** Import memory exports, merge and dedupe them, spot conflicts, and export a signed, budgeted memory file with injected instructions filtered out.

## Quickstart

Customers receive a release archive with the wheel and the examples. Python 3.10+ and no other dependencies.

```bash
pip install memory_box-0.1.0-py3-none-any.whl
memory-box import examples/chatgpt-memory.txt --source chatgpt -o box.json
memory-box import examples/claude-memory.md --source claude -o box.json
memory-box conflicts box.json
```

## Web app and API

Every command is also a JSON API endpoint and a browser form, served by the built-in web app.

```bash
memory-box-web --port 8000          # then open http://127.0.0.1:8000
docker build -t memory-box . && docker run -p 8000:8000 -v memory-box-data:/data memory-box
```

Endpoints: `POST /api/import`, `POST /api/conflicts`, `POST /api/export`, plus `GET /healthz` and `GET /api/spec` (machine-readable field list).
Files are sent as `{"name": ..., "content": ...}`, folders as `{"files": [...]}` or a base64 zip.

## Pricing

Every plan starts with a 14-day free trial. Prices in USD, billed monthly unless noted.

| Plan | Price | Includes |
|---|---|---|
| **Personal** | $5 per month | Unlimited imports; Merge and conflict check; Signed export |
| **Pro** | $12 per month | Category controls; Sensitive-data redaction; Version history |
| **Lifetime** | $99 one-time | Pro forever |

To start a trial or buy a plan, email **sales@YOUR-DOMAIN.com**.

## Licence

Proprietary. Copyright (c) 2026 eliem08. All rights reserved. Use requires a paid plan or an active trial; see [LICENSE](LICENSE).
<!-- sell-kit:end -->

## What it does

- **Portable Memory Format (PMF)**: JSON with typed facts
  `{id, text, category, source, created, confidence, sensitive}` and an HMAC signature
- **Importers**: plain-text memory lists (one fact per line / bullet — what ChatGPT
  "Manage memory" and Claude memory exports look like), Markdown, JSONL
- **Auto-categorise**: identity, preferences, work, projects, people, health, location, style
- **Merge** across sources with near-duplicate detection (token Jaccard) —
  keeps the most recent, records all sources
- **Conflict detection** for single-valued attributes ("lives in Paris" vs "lives in Lyon")
- **Export** as Markdown, JSON, or a **system-prompt block** with a token
  budget, category filter and sensitive-fact redaction

## Quickstart

```bash
pip install -e .
memory-box import chatgpt-memory.txt --source chatgpt -o box.json
memory-box import claude-memory.md --source claude -o box.json
memory-box conflicts box.json
memory-box export box.json --format prompt --budget 400 --no-sensitive
```

## Roadmap

- Encrypted sync (end-to-end; keys stay on device)
- MCP server so any agent can `memory.search` / `memory.add` with per-agent scopes
- Push-back: write merged memory into each assistant via their APIs where possible

## Development

Zero runtime dependencies; Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m unittest discover -s tests -t .           # unit + CLI smoke tests
ruff check . && ruff format --check .               # lint + format
```

```
memory_box/core.py       domain logic (pure, importable, fully tested)
memory_box/__main__.py   CLI (`memory-box ...` / `python -m memory_box ...`)
tests/                unit tests + generated CLI smoke tests
examples/             sample inputs used by the docs and smoke tests
```

CI runs lint and tests on Ubuntu and Windows across Python 3.10, 3.12 and 3.13.
Design, data model, trade-offs and production path: **[ARCHITECTURE.md](ARCHITECTURE.md)**.

Part of the [agent-economy](https://github.com/eliem08/agent-economy) portfolio (idea #22).
