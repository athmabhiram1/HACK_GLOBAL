# BatonGate — Comprehensive Architecture (HackGlobal 2026)

> Single source of truth for builders. Supersedes `02-architecture-legacy.md` (kept for history in `_archive/`).
> Stack: fork `hackglobal-starter/templates/chat-app`. No new framework. Single 2GB Vultr VM.
> Track: Open Innovation primary; secondaries Agentic (Deps) + Grounded RAG (Docs).
> Core = 5 gates (Secrets → Deps → Docs → Cost → Build). Exa fix-links + Wispr voice are OPTIONAL extras: evidence/input only, never gate the verdict.

## 0. What you are building (one page)
Paste repo URL → 0-100 Launch Score + SHIP / FIX / BLOCKED + evidence bundle in <3 min.
5 core gates run in order on throwaway Docker sandboxes on the same VM: Secrets → Deps → Docs → Cost → Build.
OPTIONAL extras (do not affect verdict): Exa fix-evidence links on critical CVEs (1 call/CVE, highlights), Wispr voice input filling the repo box (text always works).
LLM (`POST https://api.vultrinference.com/v1/chat/completions`, bearer server-side, 10s timeout) only summarizes; never gates. Every claim needs log / SARIF / quote / citation.
Frontend: full dashboard (score ring, 5 core gate cards + optional Exa/Wispr row, $ widget, drift list, SARIF download, log tail), desktop + mobile.
Deploy: `http://<vultr-ip>` via Docker `-p 80:8000`, firewall 80/443, `.env` on server only.

## 1. Starter fork map (what to keep / delete / add)
Keep from `templates/chat-app`: `main.py` FastAPI skeleton (`GET /` static, `GET /health {status:ok,model}`, `POST` pattern), `Dockerfile` (`python:3.12-slim`, `EXPOSE 8000`, `uvicorn main:app --host 0.0.0.0 --port 8000`), `requirements.txt` base (`fastapi>=0.115`, `uvicorn[standard]>=0.30`, `openai>=1.40`, `python-dotenv>=1.0`), `.env.example` pattern (`LLM_BASE_URL/API_KEY/MODEL`, never commit `.env`), `static/index.html` pattern (log div + form fetch + error div).
Delete: `templates/research-agent`, `templates/streamlit-demo` (do not ship).
Add core:
```
backend/app/main.py          # FastAPI: /api/healthz, POST /api/gate, GET /api/jobs/{id}, StaticFiles fallback
backend/app/parsers.py       # allowlist github/gitlab, Dockerfile/compose/env/port parsing
backend/app/secrets_gate.py  # gitleaks wrapper
backend/app/deps_gate.py     # OSV + typosquat + reachability
backend/app/docs_gate.py     # diff vs README, [file:line] + offsets
backend/app/cost_gate.py     # Vultr API read-only + sim
backend/app/build_gate.py    # docker build/run + healthz probe
backend/app/verdict.py       # score + SHIP/FIX/BLOCKED + exit 0/1
backend/app/inference.py     # Vultr Inference summary-only
backend/tests/test_*.py      # sync TestClient, mocked externals
frontend/ (or backend static) # dashboard: form + score + cards + SARIF + logs
samples/                     # 3 broken repos + requirements.vuln.txt + pre-recorded logs
deploy/                      # Caddy/Nginx, firewall, update script
```
Add OPTIONAL (only after core green; never block verdict):
```
backend/app/exa_gate.py      # OPTIONAL: fix-links per critical CVE, highlights evidence
backend/app/voice_gate.py    # OPTIONAL: Wispr voice → transcript fills repo box
```
Env additions: `VULTR_API_KEY` (in-memory only, never log), `DEMO_MODE=1` forces `?demo=1` synthetics, `JOB_CONCURRENCY=1`, `GITLEAKS_VERSION=8.18.4`. Optional only: `EXA_API_KEY`, `WISPR_API_KEY` (server-side, missing key = extras skipped, verdict unaffected).

## 2. API shapes (exact)
- `GET /api/healthz` → `200 {"status":"ok"}`. Used by deploy check + video.
- `POST /api/gate {"repo_url":"https://github.com/..."} ` → `202 {"job_id":"...","status":"queued"}`. Rejects non-allowlist / >50MB / submodule with `400 {error, fix_hint}` + demo suggestion.
- `GET /api/jobs/{id}` → `{"job_id","status":"queued|running|done","score":0-100,"verdict":"SHIP|FIX|BLOCKED","gates":[...],"sarif_path":"/artifacts/<id>.sarif","inference_summary":"...","demo_mode":false,"exa_links":[],"voice_transcript":null}`. `exa_links`/`voice_transcript` are OPTIONAL extras (empty/null when keys missing) and never affect score/verdict.
- Errors never 500 on gate failure: gate fail → `status done, verdict FIX/BLOCKED` with evidence; only malformed request → 4xx.
- Tests use `with TestClient(app) as client:` (runs lifespan); no async fixtures.
- Queue is a single-worker `asyncio.Queue(maxsize=1)` bound to the lifespan context manager (spawn worker with `asyncio.create_task` before `yield`, cancel after). Do NOT use FastAPI `BackgroundTasks` for the pipeline — it fires parallel jobs with no backpressure and loses tasks on restart. `POST /api/gate` returns 429 when full. All CPU-bound/subprocess work (Levenshtein, git diff, gitleaks, hadolint, docker) runs via `asyncio.to_thread` so polling/healthz never stall.

## 3. Gate contracts (copy-pasteable, each with fallback)
### 3.1 Secrets (gitleaks 8.18.4 SARIF)
`docker run --rm -v /tmp/<job>:/repo zricethezav/gitleaks:8.18.4 detect --source /repo --redact --no-banner --max-decode-depth=0 --max-target-megabytes=10 --report-format sarif --report-path /repo/gitleaks.sarif --exit-code 1` (add `--no-git` for snapshot-only; depth-0 avoids the documented 24GB recursive-decode OOM on big repos).
Success: exit 1 + valid SARIF (`sarifLog.runs[].results[]` with `ruleId,level,message,locations[].physicalLocation.{artifactLocation.uri,region.startLine}`); clean → exit 0, empty results. UI shows redacted matches only + "potential exposure, not verified active key" note. Fallback: allowlist path note, still verdicts.
### 3.2 Deps (OSV + typosquat + reachability)
Parse only `requirements.txt` / `package-lock.json` (no install). `POST https://api.osv.dev/v1/querybatch {"queries":[{"package":{"name","ecosystem":"PyPI|npm"},"version":"..."}]}` (single batched payload) → ordered `[{results:[{id,modified}]|{}}]`; then `GET https://api.osv.dev/v1/vulns/{id}` for CVSS/severity/aliases/fixed on critical only. Cache 24h. Typosquat: normalize first (lowercase, strip `-_`, homoglyph map), then Levenshtein ≤2 via `Levenshtein` C-extension package (pure-Python DP is O(m×n) per pair — 100 deps × 200 entries blocks the loop) + low-download + recent-publish heuristic. Reachability: `ast.parse` (py) / import regex (js) → reachable boosts weight. Score `0.6*CVSS + 0.3*reach + 0.1*typo` per dep, gate score = worst. Offline fallback: `samples/requirements.vuln.txt` (jinja2@2.4.1 flagged). Parsers: prefer `hadolint -f json` AST (DL3007 latest-tag, DL3011 ports), regex fallback when binary missing.
### 3.3 Docs (diff, no network)
`git diff HEAD~3 -- README.md docs/ src/` vs code endpoints; stale endpoint → `{file,line,startColumn,offset,expected,found,proposed_patch}`; no evidence → `{refused:true, reason}`. LLM never decides.
### 3.4 Cost (Vultr read-only)
`GET https://api.vultr.com/v2/instances|/sizes|/volumes|/snapshots` bearer `VULTR_API_KEY`, `monthly_cost` from `/sizes|/plans`; rules idle CPU<5%, unattached volume, oversized plan → `{current $/mo, simulated $/mo, saved, co2_kg, downgrade_cmd}`. Key in-memory only. `?demo=1` synthetic JSON fallback.
### 3.5 Build (sandboxed, last)
`git clone --depth 1 <allowlist> 60s` (hardened: `https://` only, deny IP-literals/private/metadata ranges via DNS-resolve check, `git -c protocol.ext.allow=never -c protocol.file.allow=never -c http.followRedirects=false clone --depth 1 --recurse-submodules=no -- <url>`, reject inputs starting with `-`, 50MB pre-check); parse Dockerfile/compose; `docker build -t baton:<jobid> .` 300s kill (180s too short for real pip installs) with throttled BuildKit (`/etc/buildkitd.toml`: `[worker.oci] max-parallelism=1`, gc `reservedSpace="512MB"` `maxUsedSpace="2GB"`, builder via `docker buildx create --use --driver docker-container --buildkitd-config /etc/buildkitd.toml`); `docker run -d -p 127.0.0.1:<RANDOM>:80 --rm --memory=512m --memory-swap=512m --cpus=0.5 --pids-limit=64 --read-only --cap-drop=ALL -u 65534 baton:<jobid>` on an isolated bridge network (do NOT combine `--network none` with `-p`: none = loopback only, publish is ignored, probe always fails — probe via mapped port on bridge, or `docker exec` curl if none is kept; match `--memory-swap` to `--memory` to disable swap thrashing); `GET http://127.0.0.1:<RANDOM>/healthz` 2s; capture `log_tail` 200 lines (redacted like SARIF); cleanup `docker rm -f` + tmp rm always. Queue: 1 worker, 429 if busy. Fallback: `samples/broken-dockerfile` pre-recorded logs labeled DEMO REPLAY.
### 3.6 OPTIONAL extras (never gate; skip cleanly without keys)
- Exa fix-evidence: per critical CVE only, `exa.search("fix "+cve, type="auto", contents={"highlights": True}, num_results=2)` server-side, 10s timeout, cap calls/job, cache; failure/no-key → OSV `fixed` string. Evidence only.
- Wispr voice input: frontend converts webm→16kHz mono PCM wav + RIFF headers + base64 entirely client-side (OfflineAudioContext; never burden the 2GB server); backend `POST /api/voice` → Wispr REST (WS later if green) with warmed keep-alive connection (warmup at startup, httpx keep-alive ≥60s) + context schema; transcript fills repo box. Text input always works; voice never blocks verdict. Flow desktop app (`POLTECH26`) may be shown dictating input in video instead of API.
### Verdict
BLOCKING (build fail, secret found, critical reachable CVE) → BLOCKED. Else score-weighted FIX/SHIP from the 5 core gates only. Bounds 0-100. Exit 0 SHIP, 1 FIX/BLOCKED for CI. Exa/Wispr/Inference never change the verdict.

## 4. Report shape (how the report looks)
JSON (`GET /api/jobs/{id}`):
```json
{
  "job_id": "a1b2",
  "score": 42,
  "verdict": "BLOCKED",
  "demo_mode": false,
  "gates": [
    {"name":"secrets","status":"fail","summary":"2 leaked keys redacted","evidence":{"found":true,"sarif_ref":"/artifacts/a1b2.sarif","redactions":2}},
    {"name":"deps","status":"warn","summary":"jinja2@2.4.1 CVE-... CVSS 9.8 reachable","evidence":{"findings":[{"pkg":"jinja2","version":"2.4.1","severity":"Critical","cvss":9.8,"reachable":true,"typo":false,"fix":"jinja2>=3.1"}],"score":18}},
    {"name":"docs","status":"warn","summary":"1 stale endpoint","evidence":{"stale":[{"file":"README.md","line":31,"offset":412,"proposed":"GET /healthz"}]}},
    {"name":"cost","status":"pass","summary":"$6.00/mo, no waste","evidence":{"current":6.0,"simulated":6.0,"saved":0.0}},
    {"name":"build","status":"fail","summary":"GET /healthz timeout, tail L120-140","evidence":{"built":true,"healthz":"fail","log_tail":"..."}}
  ],
  "inference_summary": "Blocked by leaked key + reachable CVE; fix key rotation + bump jinja2, rebuild.",
  "artifacts": {"sarif":"/artifacts/a1b2.sarif","log":"/artifacts/a1b2.log"}
}
```
SHIP example: score ≥80, all pass, summary "Ready to ship on Vultr".
Dashboard: top score ring + verdict pill; 5 core cards (status color, summary, evidence link); OPTIONAL row (Exa links + voice transcript, hidden when unavailable); $ widget ($ now → $ sim, saved/mo, CO2); drift list with [file:line]; buttons SARIF download + copy fix diff + rebuild; log tail <pre> (redacted). Mobile: cards stack, ring shrinks.

## 5. Features checklist (what to build)
CORE (verdict path): Parsers (allowlist, Dockerfile/compose/env/ports, localhost:3000, latest tag); Secrets (scan, redact, SARIF download); Deps (upload/paste requirements, OSV batch, typosquat flag, reachability badge, fix version); Docs (diff view, stale list, patch copy); Cost (Vultr connect/read-only, table idle/oversize, downgrade cmd, demo toggle); Build (repo input, progress, healthz 200 proof, redacted log tail); Verdict (score, SHIP/FIX/BLOCKED from 5 core only, exit code); Dashboard (form, polling, 5 cards, widgets, downloads); Deploy (Dockerfile, Caddy/Nginx, firewall, update script); Submission (README, diagram, video script, checklist).
OPTIONAL (extras, only after core green): Exa fix-links row (2 links + highlights per critical CVE, skip without key); Voice mic button (transcript fills input, text always works, Flow desktop as video alternative).

## 6. Waves (build in this order, no roadblocks)
- Wave 0 — Skeleton (Sat AM): FastAPI healthz + gate stub + static form; exit: `curl /api/healthz 200`, form POST shows queued JSON. Fallback StaticFiles.
- Wave 1 — Secrets+Deps ironclad (Sat midday): parsers + gitleaks + OSV mocked→real; exit: `pytest test_parsers test_secrets test_deps` green + offline samples verdict. Do not start Build until green.
- Wave 2 — Docs+Cost + deploy live (Sat eve): diff + Vultr read-only + `?demo=1`; deploy 2GB VM, private-window live check; exit: live URL 200 + E2E demo job.
- Wave 3 — Build guarded (Sat night): fake-docker unit → real docker behind queue/300s kill, bridge probe (see §3.5); exit: mocked 200/timeout-cleanup + 1 real build log + DEMO REPLAY bundle.
- Wave 4 — Verdict+Inference+dashboard core (Sun AM): rules + redacted summary + 5-card UI; exit: `pytest -v` green + SHIP + BLOCKED samples + desktop/mobile screenshots. OPTIONAL extras only after core green: Exa row, voice button.
- Wave 5 — Submission (Sun ≤10:00): public repo + README + diagram + video (fail→200 curl) + Vultr Community form (tag Hackathons + HackGlobal 2026).
Each wave lists files, tests, QA command, evidence path, fallback. Stop-if-red per wave.

## 7. Vultr deploy (exact)
`ssh root@IP; curl -fsSL https://get.docker.com | sh; apt-get install -y git hadolint; git clone <repo>; cp .env.example .env; nano .env (LLM + optional VULTR keys); printf '[worker.oci]\n max-parallelism=1\n[worker.oci.gcpolicy]\n reservedSpace="512MB"\n maxUsedSpace="2GB"\n' | sudo tee /etc/buildkitd.toml; docker buildx create --use --driver docker-container --buildkitd-config /etc/buildkitd.toml; sudo iptables -I DOCKER-USER -d 169.254.169.254 -j REJECT; docker build -t baton .; docker run -d --restart unless-stopped --env-file .env -p 80:8000 baton; ufw allow 80/tcp; open http://IP`. REJECT (not DROP) on the metadata IP so probes fail fast instead of eating the build timeout; UFW alone is bypassed by Docker, the DOCKER-USER rule is the real guard. Update: `git pull; docker rm -f baton; docker build -t baton .; docker run ...`. Keep key out of image/bundle. Destroy or add payment after judging.

## 8. Risks → fallback (never 500)
SSRF/huge/submodule → reject + FIX + demo (https-only, no ext/file protocol, no redirects, `-` args rejected, size pre-checked). Private repo/binary → clear FIX + demo. OSV/Vultr down → cache/samples/demo. FP → redacted + allowlist. OOM → queue + 429. Inference down → static summary. Exa/Wispr down or no key → extras skipped silently, verdict from 5 core gates unchanged.

## 9. File tree after docs build
```
docs/
  PLAN.md 02-architecture.md(this) 03-starter-guide.md 04-report-spec.md 05-submission.md README.md
  _archive/ (01-prd, 02-architecture-legacy, 03a, 03b, 05a, 05b, 06, 07, 08 — history only)
```
Root originals kept; `docs/` is the read-first folder for agents.

Sources: OSV querybatch/schema, SARIF 2.1.0/sarif.info, Exa search/highlights, FastAPI testing-events, safeguard typosquat, Vultr API/Inference quickstart, starter templates.
