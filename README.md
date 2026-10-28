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
memory-box-web keys create --label "first customer"   # prints an API key (stored hashed)
docker build -t memory-box . && docker run -p 8000:8000 -e API_KEYS=sk_... -v memory-box-data:/data memory-box
```

Every API call needs `Authorization: Bearer <key>` once any key exists; a server on a public address refuses to start without one. Calls are rate-limited per key (60/min, `--rate`) and metered: `memory-box-web usage` prints calls per key for billing.

Endpoints: `POST /api/import`, `POST /api/conflicts`, `POST /api/export`, plus `GET /healthz` and `GET /api/spec` (machine-readable field list).
Files are sent as `{"name": ..., "content": ...}`, folders as `{"files": [...]}` or a base64 zip.

## Deploy and sell

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/eliem08/memory-box)

`render.yaml` (one click, above) and `fly.toml` (`fly launch --copy-config`) both run the Dockerfile with a persistent `/data` volume and a `/healthz` check.
To sell self-serve, set four variables and point a Stripe webhook at `https://<your-host>/billing/webhook` (events `checkout.session.completed` and `customer.subscription.deleted`):

| Variable | Example |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` |
| `STRIPE_PRICES` | `personal=<personal-price-id>,pro=<pro-price-id>,lifetime=<lifetime-price-id>` |
| `PUBLIC_URL` | `https://memory-box.example.com` |

Buyers pick a plan on `/pricing`, pay on Stripe Checkout and see their API key once on the success page. Monthly plans start with a 14-day free trial; Lifetime is a one-time payment. Cancelling the subscription revokes the key. A selling server always requires a key. Copy `.env.example` to `.env` for the variable names; never commit real values.

## Pricing

Every plan starts with a 14-day free trial. Prices in USD, billed monthly unless noted.

| Plan | Price | Includes |
|---|---|---|
| **Personal** | $5 per month | Unlimited imports; Merge and conflict check; Signed export |
| **Pro** | $12 per month | Everything in Personal; Commercial use; Priority support |
| **Lifetime** | $99 one-time | Pro forever |

All plans unlock the same software; higher tiers add licence scope and support, not gated features. Category controls (`--categories`) and sensitive-data redaction (`--no-sensitive`) are part of the software on every plan.

To start a trial or buy a plan, [request access](https://github.com/eliem08/memory-box/issues/new?title=Memory%20Box%20trial&labels=sales).

## Licence

Proprietary. Copyright (c) 2026 eliem08. All rights reserved. Use requires a paid plan or an active trial; see [LICENSE](LICENSE).
<!-- sell-kit:end -->

## What it does

- **Portable Memory Format (PMF)**: JSON with typed facts
  `{id, text, category, sources, created, confidence}` and an HMAC signature
  when `MEMORY_BOX_KEY` is set (without it the file is unsigned; `sensitive`
  is derived from the category, not stored)
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

- Version history (box snapshots)
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
