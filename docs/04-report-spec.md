# Report Spec — JSON + dashboard + SARIF (exact)

## Report JSON (GET /api/jobs/{id})
Fields: `job_id, status, score 0-100, verdict SHIP|FIX|BLOCKED, demo_mode bool, gates[5]{name,status pass|warn|fail,summary,evidence}, inference_summary, artifacts{sarif,log}` + OPTIONAL `exa_links[]`, `voice_transcript` (empty/null when keys missing, never affect score).
Evidence keys: build `{built,healthz,log_tail(redacted)}`, secrets `{found,sarif_ref,redactions}`, deps `{findings[{pkg,version,severity,cvss,reachable,typo,fix}],score}`, cost `{current,simulated,saved,co2,downgrade_cmd}`, docs `{stale[{file,line,offset,proposed}],refused}`.

### SHIP example
`score 92, verdict SHIP, all pass, cost saved 0, inference_summary "Ready to ship on Vultr."`
### BLOCKED example
See `02-architecture.md` §4 (score 42, secrets fail + deps warn + build fail).

## Dashboard layout
Header: repo input + Analyze button + demo toggle (+ mic button only when voice enabled). Body: score ring (0-100) + verdict pill; 5 gate cards (color, summary, evidence link/quote); OPTIONAL Exa/Wispr row (hidden when unavailable); $ widget (`$now → $sim`, saved/mo, CO2); drift list (`file:line` + patch copy); footer: SARIF download, log `<pre>` tail 200 lines, rebuild button. States: queued (spinner), running (per-gate progress), done (cards), error (4xx message + demo hint). Desktop `max-width 720` centered; mobile stacks cards, ring 50%.

## SARIF (gitleaks output, valid)
`sarifLog.version 2.1.0, runs[{tool.driver{name:gitleaks,rules[]}, results[{ruleId,level:error|warning,message{text},locations[{physicalLocation{artifactLocation{uri},region{startLine,startColumn}}}]}]}]`. Store at `/artifacts/<job>.sarif`; link from report; never inline secrets (redacted).

## Inference summary prompt (redacted)
System: "Summarize gate results in 2 sentences, list fixes. No new verdicts." User: redacted gate summaries only (no keys, no full logs). Timeout 10s; on fail use static `"Blocked by ...; fix ..."` template.
