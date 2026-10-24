# memory-box

[![CI](https://github.com/eliem08/memory-box/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/memory-box/actions/workflows/ci.yml)

> **Dropbox for your AI memory** — take what your agent knows about you to any agent.

ChatGPT knows you're vegetarian. Claude knows your codebase conventions.
Your new agent knows nothing. `memory-box` defines a portable memory format,
imports from each assistant's export, merges and de-duplicates, flags
conflicts, and exports a compact context block any agent can load.

## What the MVP does

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
