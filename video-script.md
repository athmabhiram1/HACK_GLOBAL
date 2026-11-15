# BatonGate — 90s demo video script (shot list)

Total 90s. Record at 1080p, desktop + one mobile insert. Keep the Vultr IP URL bar visible in every live shot. No secrets on screen (keys server-side, SARIF/log shown redacted).

## 0:00–0:15 — Problem (15s)

- Shot 1 (0–15s): Talking head / title card: "Vibe-coded repos ship fast and break on launch — leaked keys, bad deps, dead Dockerfiles." Show 3 broken `samples/` repos list on screen.
- On-screen text: `BatonGate: paste URL → score + SHIP/FIX/BLOCKED in <3 min`.
- Must be visible: project name, the 3 sample repo names.

## 0:15–1:00 — Live-IP run (45s)

- Shot 2 (15–30s): Browser opens `http://<vultr-ip>/` — URL bar with the live IP clearly visible. Paste a repo URL into the dashboard form, hit Scan. Show `202 {"job_id":...,"status":"queued"}` in DevTools Network OR the dashboard "queued → running" state.
- Shot 3 (30–45s): Terminal side-by-side with browser. A second tab shows the Vultr Console / `docker ps` container (`baton`) running — proves one 2GB VM. Run:

  ```bash
  curl -s http://<vultr-ip>/api/healthz
  # expect: {"status":"ok"}
  ```

  Must be visible: URL bar with IP, `docker ps` showing `baton`, `curl /api/healthz` returning 200 `{"status":"ok"}`.

- Shot 4 (45–60s): Poll the gate job live:

  ```bash
  curl -s -X POST http://<vultr-ip>/api/gate \
    -H 'Content-Type: application/json' \
    -d '{"repo_url":"https://github.com/YOU/demo-repo"}'
  # expect: 202 {"job_id":"...","status":"queued"}

  curl -s http://<vultr-ip>/api/jobs/<job_id>
  # expect: status running -> done, score 0-100, verdict SHIP|FIX|BLOCKED
  ```

  Must be visible: dashboard progress → score ring filling, 5 core gate cards updating.

## 1:00–1:30 — Verdict + evidence + $ sim + citations (30s)

- Shot 5 (60–75s): Final verdict screen: score + SHIP/FIX/BLOCKED pill + 5 gate cards. Click **Download SARIF**, scroll the redacted `log_tail`. Show the $ widget (`current → simulated`, saved/mo).
- Shot 6 (75–90s): Docs drift list with `[file:line]` + Exa fix-link citations on a critical CVE (or "skipped — no key" row when absent). Closing card: live URL + GitHub link + "Built on Vultr Compute 2GB + Inference".
- Must be visible: verdict pill, SARIF download click, $ simulation numbers, CVE + citation (or honest skipped state).

## Recording checklist

- [ ] Private/incognito window for the live-IP run.
- [ ] No `.env` / keys on screen at any point.
- [ ] Healthz `curl` returns 200 on camera.
- [ ] One full gate job reaches `done` on camera.
- [ ] Mobile viewport insert (cards stack) — 3s minimum.
- [ ] Export ≤4MB stills for the Community form (up to 5 images, PNG/JPG).
