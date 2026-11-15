# BatonGate — paste a vibe-coded repo URL, get a launch verdict in <3 min.

**Live demo:** http://VIDEO_URL_TBD (Vultr IP goes live on deploy) · **Demo video:** VIDEO_URL_TBD · **Track:** Open Innovation (HackGlobal 2026)

## The problem

Vibe-coded repos ship fast and break fast: leaked keys, vulnerable deps, stale docs, surprise cloud bills, and Dockerfiles that don't build. Solo founders discover this after deploy, when fixes are most expensive.

## Our solution

BatonGate runs 5 core gates — Secrets, Deps, Docs, Cost, Build — on one 2GB Vultr VM and returns a 0–100 Launch Score plus SHIP / FIX / BLOCKED with an evidence bundle (SARIF, CVE citations, $ simulation, redacted build log). Exa fix-links and Wispr voice input are optional extras that never change the verdict.

## How it works

```
browser → FastAPI + single-worker queue (asyncio.Queue maxsize=1, 429 when busy)
            → 5 core gates, each in a throwaway Docker sandbox
               [secrets (gitleaks SARIF)] → [deps (OSV+typosquat+reachability)]
               → [docs (git diff vs README)] → [cost (Vultr API read-only)]
               → [build (clone harden → build 300s → probe /healthz)]
            → verdict (score 0-100, SHIP/FIX/BLOCKED, never 500)
            → optional row: [Exa fix-links] [Wispr voice transcript] (evidence/input only)
```

- Queue: single worker bound to lifespan; all blocking work via `asyncio.to_thread`.
- Clone hardening: `https://` only, deny IP-literals/private/metadata ranges via DNS check, `git -c protocol.ext.allow=never -c protocol.file.allow=never -c http.followRedirects=false clone --depth 1 --recurse-submodules=no -- <url>`.
- LLM (Vultr Inference) only summarizes redacted results (10s timeout, static fallback); every gate has an offline/demo fallback.

## Built with

- Vultr Compute 2GB VM (API + sandboxes, one box) + Vultr Inference (summary only, model pinned from `GET /v1/models`) + Vultr API v2 (read-only cost gate)
- Exa (optional fix-evidence links, 1 call/critical CVE) + Wispr (optional voice input, REST)
- Docker Engine + BuildKit throttle (`max-parallelism=1`, gc caps) + gitleaks 8.18.4 SARIF + OSV.dev querybatch + hadolint
- Python 3.12, FastAPI, httpx, exa-py, Levenshtein

## Run it locally

```bash
git clone https://github.com/athmabhiram1/HACK_GLOBAL.git
cd HACK_GLOBAL
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # fill on your machine; never commit .env
pytest backend/tests -v
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
# open http://127.0.0.1:8000  ·  health: curl http://127.0.0.1:8000/api/healthz
```

Env names only (keys stay server-side): `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `VULTR_API_KEY`, `EXA_API_KEY`, `WISPR_API_KEY`, `DEMO_MODE`, `BATON_LIVE_BUILD`, `JOB_CONCURRENCY`, `GITLEAKS_VERSION`.

Deploy on Vultr: `bash deploy/update.sh <repo-url>` (see `docs/02-architecture.md` §7). Credits: starter template + OSS (FastAPI, gitleaks, OSV) + Exa + Wispr.

## Team

| Name | University | Role |
| ---- | ---------- | ---- |
| Solo builder | — | Design, backend, deploy, video |

## What's next

Post-hackathon: pinned-model auto-refresh, SARIF upload history per repo, scheduled re-scan cron, cost-gate snapshots API, hosted multi-region probe.
