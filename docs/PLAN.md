# BatonGate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Solo 36h — paste a vibe-coded repo URL, get a 0-100 Launch Score + SHIP/FIX/BLOCKED + evidence bundle in <3 min on one 2GB Vultr VM with public URL, GitHub, diagram, and video.

**Architecture:** Fork `hackglobal-starter/templates/chat-app` (FastAPI + static). Single Vultr Compute VM runs API + one single-worker job queue; each of 5 CORE gates runs in a throwaway Docker sandbox. Parsers + OSV + Vultr APIs decide; Vultr Inference only summarizes. OPTIONAL extras (Exa fix-links, Wispr voice input) add evidence/input only and never change the verdict. Every gate has an offline/demo fallback and returns evidence, never 500.

**Tech Stack:** Python 3.12, FastAPI + httpx TestClient (sync, `with TestClient(app)`), Docker Engine, gitleaks 8.18.4 SARIF, OSV.dev querybatch, exa-py, Vultr API v2 + Vultr Inference OpenAI-compatible, Wispr REST (WS later), Caddy/Nginx, pytest.

**Spec:** `docs/02-architecture.md` (binding) + `docs/03-starter-guide.md` (fork map) + `docs/04-report-spec.md` (report/SARIF) + `docs/05-submission.md` (Vultr form). Detail copies live in `docs/_archive/` (history only — do not build from them).

## Global Constraints
- Track: Open Innovation primary (secondaries: Deps→Agentic, Docs→Grounded RAG, Cost→real-world impact, Exa→research, Wispr→Multimodal).
- One VM: 2 vCPU/2GB (~$12/mo, 36h ≈ $0.65, covered by $200 credits). No K8s, no Managed DB, no GPU. Firewall 80/443 only.
- No secrets in GitHub/sandbox/frontend/logs; API keys server-side only, non-root sandbox user.
- Queue is a single-worker `asyncio.Queue(maxsize=1)` bound to lifespan (spawn worker before `yield`, cancel after). Never use `BackgroundTasks` for the pipeline. 429 when full. All blocking work via `asyncio.to_thread`.
- Clone hardening: `https://` only, deny IP-literals/private/metadata ranges via DNS-resolve check, `git -c protocol.ext.allow=never -c protocol.file.allow=never -c http.followRedirects=false clone --depth 1 --recurse-submodules=no -- <url>`, reject inputs starting with `-`, pre-check size, redact `log_tail` like SARIF.
- LLM (Vultr Inference) never gates — summarizes redacted results only, 10s timeout, static fallback.
- Exa (OPTIONAL extra): max 1 call per critical CVE, `type="auto"`, `contents={"highlights": True}`, server-side key, failure/no-key → skipped, verdict from 5 core gates unchanged.
- Wispr (OPTIONAL extra): REST first with backend key; browser records webm → convert to 16kHz PCM wav base64; text input always works; voice never blocks verdict.
- Tests first: sync pytest + TestClient, watch RED before GREEN. Mock externals in unit tests.
- Submission: public GitHub + setup README, live `http://<vultr-ip>` working in private window, arch diagram, tag Hackathons + Build for HackGlobal 2026, video 90s, submit ≥1h before Sun 12:00 IST.

## Review Focus
- Arbitrary repo URL → SSRF/huge/submodule bomb → expect reject with 400 + fix hint + demo suggestion, never hang. (Task 2 test.)
- Private repo / binary / timeout mid-build → expect FIX/BLOCKED with DEMO REPLAY log labeled as replay, never 500. (Task 7 test.)
- OSV/Exa/Vultr/Wispr/Inference down → expect cached/samples/static-summary verdict, never crash. (Tasks 4–6, 8 tests.)
- gitleaks false positive or real secret → expect redacted evidence + SARIF download, secret never in UI/logs. (Task 3 test.)
- Two jobs at once on small VM → expect second gets 429 + retry hint, never parallel builds. (Task 7 test.)

---

### Task 1: Skeleton + health + deployable image
**Files:**
- Create: `backend/app/main.py`, `backend/tests/test_health.py`, `backend/requirements.txt`, `Dockerfile`, `.env.example`
- Test: `backend/tests/test_health.py`
**Interfaces:**
- Consumes: starter `templates/chat-app/main.py:28-61`, `Dockerfile:1-7`
- Produces: `GET /api/healthz → 200 {"status":"ok"}`, `GET /` static, job-queue stub interface used by all later tasks
- [ ] Step 1: Write failing test `test_healthz_200` (200 + status ok) and `test_root_serves_form` (200 html).
- [ ] Step 2: Run `pytest backend/tests/test_health.py -v` Expected: FAIL, app not defined.
- [ ] Step 3: Implement `main.py` FastAPI from starter skeleton + `/api/healthz`; Dockerfile `python:3.12-slim EXPOSE 8000` (+ `hadolint` install on VM per `02-architecture.md` §7); requirements `fastapi uvicorn openai python-dotenv httpx exa-py Levenshtein pytest`.
- [ ] Step 4: Run pytest Expected: PASS pristine.
- [ ] Step 5: Commit. ✅ DONE — 2/2 green, committed.

### Task 2: Repo intake + static parsers (no exec)
**Files:**
- Create: `backend/app/parsers.py`, `backend/tests/test_parsers.py`
- Test: `backend/tests/test_parsers.py`
**Interfaces:**
- Consumes: Task 1 app (mount router).
- Produces: `parse_repo_input(url)`, `parse_dockerfile/compose/env()` → `{dockerfile, compose, ports, localhost_refs, latest_tag}`; `POST /api/gate` validation errors `{error, fix_hint}`.
- [ ] Step 1: Write failing tests: rejects non-allowlist host; detects missing EXPOSE, hardcoded localhost:3000, `latest` tag; >50MB/submodule rejected.
- [ ] Step 2: Run `pytest backend/tests/test_parsers.py -v` Expected: FAIL.
- [ ] Step 3: Implement pure parsers with fixtures in `samples/` (no clone yet). Prefer `hadolint -f json` AST (DL3007 latest, DL3011 ports), regex fallback when binary missing.
- [ ] Step 4: Run pytest Expected: PASS.
- [ ] Step 5: Commit. ✅ DONE — 12/12 green (incl. broken-fixture test), committed.

### Task 3: Secrets gate (gitleaks SARIF, redacted)
**Files:**
- Create: `backend/app/secrets_gate.py`, `backend/tests/test_secrets.py`
- Test: `backend/tests/test_secrets.py`
**Interfaces:**
- Consumes: Task 2 parsed dir.
- Produces: `scan_secrets(repo_dir) → {found: bool, sarif_path, redactions: int}`.
- [ ] Step 1: Write failing tests: planted fake key found + redacted in output; clean repo passes; SARIF parses with `sarifLog.runs[].results[]`.
- [ ] Step 2: Run pytest Expected: FAIL.
- [ ] Step 3: Implement wrapper `zricethezav/gitleaks:8.18.4 detect --source /repo --redact --no-banner --max-decode-depth=0 --max-target-megabytes=10 --report-format sarif --report-path /repo.sarif --exit-code 1` (add `--no-git` for snapshot-only; depth-0 avoids OOM on big repos); never log raw secret; append "potential exposure" note.
- [ ] Step 4: Run pytest Expected: PASS.
- [ ] Step 5: Commit. 🔄 IN PROGRESS (rebuilding after disk loss).

### Task 4: Deps gate (OSV + typosquat + reachability)
**Files:**
- Create: `backend/app/deps_gate.py`, `backend/tests/test_deps.py`
- Test: `backend/tests/test_deps.py`
**Interfaces:**
- Consumes: Task 2 parsed manifests.
- Produces: `score_deps(reqs) → {score 0-100, findings[{pkg,version,severity,cvss,reachable,typo,fix}]}`.
- [ ] Step 1: Write failing tests (mocked `querybatch`): `jinja2@2.4.1` flagged; `reqeusts` typosquat flagged; unreachable scores lower than reachable; offline cache fallback works.
- [ ] Step 2: Run pytest Expected: FAIL.
- [ ] Step 3: Implement parse-only (no install); `POST https://api.osv.dev/v1/querybatch` single batched payload + `GET /v1/vulns/{id}` critical only, cache 24h; normalize (lowercase, strip `-_`, homoglyph map) then Levenshtein ≤2 via `Levenshtein` C-extension (add to requirements, pure-Python DP is O(m×n) per pair) vs top-200; `ast.parse`/import-regex reachability; score `0.6*CVSS+0.3*reach+0.1*typo`.
- [ ] Step 4: Run pytest Expected: PASS.
- [ ] Step 5: Commit.

### Task 5: Exa fix-evidence (OPTIONAL extra, never gates)
**Files:**
- Create: `backend/app/exa_gate.py`, `backend/tests/test_exa.py`
- Test: `backend/tests/test_exa.py`
**Interfaces:**
- Consumes: Task 4 critical findings.
- Produces: `fix_links(cve_id) → [{url, title, highlights[2]}]`; missing key/failure → `[]`, verdict unaffected.
- [ ] Step 1: Write failing tests (mocked exa-py): returns 2 links + highlights; timeout → falls back to OSV `fixed` string; no key → skipped without failing gate or changing score.
- [ ] Step 2: Run pytest Expected: FAIL.
- [ ] Step 3: Implement `exa.search("fix "+cve, type="auto", contents={"highlights": True}, num_results=2)` server-side, 10s timeout, cap calls/job (unbounded calls burn the $20 credits), cache. OPTIONAL — build only after Tasks 1–4 green.
- [ ] Step 4: Run pytest Expected: PASS.
- [ ] Step 5: Commit.

### Task 6: Docs + Cost gates (read-only)
**Files:**
- Create: `backend/app/docs_gate.py`, `backend/app/cost_gate.py`, `backend/tests/test_cost_docs.py`
- Test: `backend/tests/test_cost_docs.py`
**Interfaces:**
- Consumes: Task 2 diff + manifests.
- Produces: `check_docs(diff) → {stale[{file,line,offset,patch}] | refused}`; `estimate_cost() → {current, simulated, saved, co2, downgrade_cmd}`.
- [ ] Step 1: Write failing tests: stale endpoint flagged with file:line+offset; no-evidence refuses; idle VM + unattached volume flagged with $ math; `?demo=1` synthetic works with no key; voice transcript path mocked (optional-only).
- [ ] Step 2: Run pytest Expected: FAIL.
- [ ] Step 3: Implement git-diff vs README (no LLM decision); Vultr `GET /v2/instances|sizes|volumes` read-only, price from /sizes, key in-memory only; OPTIONAL voice `POST /api/voice` last (client-side webm→wav16k base64, warmup `GET /api/v1/dash/warmup_dash` + httpx keep-alive ≥60s, WS later) — text input always works.
- [ ] Step 4: Run pytest Expected: PASS.
- [ ] Step 5: Commit.

### Task 7: Build gate, single-worker queue (last, guarded)
**Files:**
- Create: `backend/app/build_gate.py`, `backend/app/queue.py`, `backend/tests/test_build.py`
- Test: `backend/tests/test_build.py`
**Interfaces:**
- Consumes: Tasks 2–6.
- Produces: `build_and_probe(job) → {built, healthz, log_tail}`; queue `submit() → 202 or 429`.
- [ ] Step 1: Write failing tests with fake docker runner: success 200; timeout → FIX with log tail; cleanup always called; second concurrent submit → 429.
- [ ] Step 2: Run pytest Expected: FAIL.
- [ ] Step 3: Implement clone with hardening flags (see Global Constraints: https-only, deny IP-literals/private/metadata ranges via DNS-resolve check, `git -c protocol.ext.allow=never -c protocol.file.allow=never -c http.followRedirects=false clone --depth 1 --recurse-submodules=no -- <url>`, reject `-` prefix, 60s/50MB pre-check) + 300s build kill (throttled BuildKit builder: `/etc/buildkitd.toml` max-parallelism=1, gc caps, `docker buildx create --use` — see `02-architecture.md` §3.5/§7) + bridge run `--rm --memory=512m --memory-swap=512m --cpus=0.5 --pids-limit=64 --read-only --cap-drop=ALL -u 65534` (swap matched to block swap-thrashing; do NOT use `--network none` with `-p` — none = loopback only, publish ignored; probe mapped port on bridge or `docker exec` curl) + redacted tail + cleanup always; DEMO REPLAY bundle from `samples/broken-dockerfile` on timeout; lifespan `asyncio.Queue(maxsize=1)` worker, 429 when busy; blocking work via `asyncio.to_thread`.
- [ ] Step 4: Run pytest Expected: PASS (mocked docker; 1 real build only on VM).
- [ ] Step 5: Commit.

### Task 8: Verdict + Inference summary + dashboard + voice input
**Files:**
- Create: `backend/app/verdict.py`, `backend/app/inference.py`, `backend/app/voice_gate.py`, `static/index.html` (dashboard), `backend/tests/test_verdict.py`
- Test: `backend/tests/test_verdict.py`
**Interfaces:**
- Consumes: Tasks 2–7 outputs.
- Produces: `POST /api/gate → 202 {job_id}`; `GET /api/jobs/{id} → {score,verdict,gates[5 core],exa_links[],inference_summary,demo_mode,voice_transcript}` (extras empty/null when unavailable, never affect score); dashboard (form, score ring, 5 core cards + optional Exa/Wispr row, $ widget, drift list, SARIF/log download, mic button); `POST /api/voice {audio_b64}` (optional).
- [ ] Step 1: Write failing tests: BLOCKED on secret/build-fail/critical-reachable (5 core gates only); score 0–100 bounds; Inference called once with redacted prompt (model pinned from `GET /v1/models`, e.g. `deepseek-v4.1-flash-1017`); timeout → static summary; voice mocked transcript fills repo field; text input works with no audio; missing Exa/Wispr keys → verdict unchanged.
- [ ] Step 2: Run pytest Expected: FAIL.
- [ ] Step 3: Implement verdict rules + `POST https://api.vultrinference.com/v1/chat/completions` (bearer server-side, redacted, 10s) + dashboard polling + OPTIONAL Wispr REST `POST /api` base64 wav16k (only after core green; WS later if green).
- [ ] Step 4: Run full `pytest -v` Expected: PASS pristine + SHIP and BLOCKED samples render.
- [ ] Step 5: Commit.

### Task 9: Vultr deploy + samples + video + submission
**Files:**
- Create: `deploy/` update script, `samples/` (3 broken repos + requirements.vuln.txt + pre-recorded logs — DONE, fixtures agent), `docs/architecture.png`, `video-script.md`, root `README.md` (from archived 05a template pattern), `shareable-summary.md`
- Test: manual E2E checklist (not pytest).
- [ ] Step 1: Pre-checks (Fri eve): Discord joined + Community onboarded + Register/Save-spot + Check-in (every member) + credits form (fresh email, same account) + `POLTECH26` redeemed + Exa registered; secret keys on server only.
- [ ] Step 2: Deploy to 2GB Ubuntu + Docker + hadolint + BuildKit throttle + metadata REJECT rule (`sudo iptables -I DOCKER-USER -d 169.254.169.254 -j REJECT` — REJECT not DROP so probes fail fast; UFW alone is bypassed by Docker) (see `02-architecture.md` §7); `git clone; cp .env.example .env` (fill on server); `docker build -t baton .`; `docker run -d --restart unless-stopped --env-file .env -p 80:8000 baton`; `ufw allow 80/tcp`; open `http://<ip>` in private window; pin Inference `model` from `GET /v1/models`, verify response `model`.
- [ ] Step 3: Run E2E: healthz 200, one full gate job → SHIP/FIX/BLOCKED + SARIF download + $ sim (+ Exa links/voice transcript when keys present); desktop + mobile screenshots (≤5 images, PNG/JPG ≤4MB each for form).
- [ ] Step 4: Record 90s video (0-15s problem, 15-60s live-IP run with URL bar + Console/container visible + `curl /api/healthz` 200, 60-90s verdict + SARIF + $ sim + citations); shareable summary card (score + verdict + drift chart) for Reach.
- [ ] Step 5: Fill Vultr Community Submit Project form (New Project → fill → Quick review ~day → Showcase; +50 approved, +300 featured): General (name ≤200 chars, 1–2 sentence desc ≤500 chars, up to 5 images), Technical (Industry/Domain dropdown, public GitHub link, live `https://` URL, Vultr setup ≤2000 chars: services + region + why), Additional (teammates via name/username/email search, Build for event = HackGlobal 2026 `01a1acc5-...` or invisible). Submit Sat night (moderator lag) and ≥1h before Sun 12:00 IST. Reach runbook Sun AM: share live + Showcase links (3+ countries clicks, logs/screenshots, Discord activity, likes/shares/votes). Finalist 7+1 deck outline ready.
- [ ] Step 6: Commit.
