# BatonGate architecture

> NOTE: export a screenshot of the live dashboard to `docs/architecture.png` on the Vultr VM
> (after a real gate run, desktop viewport). This mermaid diagram is the source of truth until then.

```mermaid
flowchart TB
    U[Browser dashboard<br/>form + score ring + 5 cards + SARIF/$ widgets] --> POSTGate[POST /api/gate]
    POSTGate -->|202 queued / 400 reject / 429 busy| Q[single-worker asyncio.Queue maxsize=1<br/>lifespan bound, to_thread work]
    Q --> S1[Secrets: gitleaks 8.18.4 SARIF<br/>--redact, fallback allowlist note]
    S1 --> S2[Deps: OSV querybatch + typosquat + reachability<br/>fallback samples cache]
    S2 --> S3[Docs: git diff vs README<br/>stale file:line or refused]
    S3 --> S4[Cost: Vultr API read-only<br/>fallback ?demo=1 synthetic]
    S4 --> S5[Build sandbox: hardened clone<br/>buildx 300s kill, bridge probe /healthz<br/>fallback DEMO REPLAY bundle]
    S5 --> V[Verdict: score 0-100 SHIP/FIX/BLOCKED<br/>5 core gates only]
    V --> LLM[Vultr Inference summary<br/>redacted, 10s timeout, static fallback]
    LLM --> R[GET /api/jobs/id: score verdict gates<br/>exa_links voice_transcript<br/>never 500 on gate failure]
    R --> U
    V -.optional evidence only.-> EXA[Exa fix-links<br/>1 call per critical CVE<br/>missing key = skipped]
    U -.optional input only.-> WIS[Wispr voice -> transcript<br/>text always works]
    EXA --> R
    WIS --> POSTGate
    S5 -.fail fast.-> META[iptables DOCKER-USER REJECT 169.254.169.254<br/>REJECT not DROP]
```

Never-500 rule: gate failure returns `status done` with `verdict FIX/BLOCKED` + evidence; only malformed requests return 4xx. Exa / Wispr / Inference never change the verdict.
