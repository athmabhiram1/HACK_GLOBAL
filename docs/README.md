# docs/ — read-first folder for BatonGate builders

Single plan: `PLAN.md` (read this first — everything an agent needs).
Binding refs: `02-architecture.md`, `03-starter-guide.md`, `04-report-spec.md`, `05-submission.md`.
History only: `_archive/` (old PRD, legacy plan, starter copies, ideas, ULW plan — do not build from them).

| File | What |
| --- | --- |
| `PLAN.md` | The plan: 9 TDD tasks Waves 0–5, contracts, cost, risks, submission |
| `02-architecture.md` | **Comprehensive architecture: starter fork, APIs, gate CLIs, verdict, report JSON, dashboard, Waves 0–5, deploy, fallbacks** |
| `03-starter-guide.md` | Fork map: keep/delete/add + env |
| `04-report-spec.md` | Report JSON + dashboard + SARIF exact (incl. optional exa_links/voice_transcript) |
| `05-submission.md` | Submission fields + video + judging (live form shape, points, Demo Day) |

Rules: implement only from `PLAN.md` + `02` + `03-starter-guide` + `04`; everything else is context. No hallucinated endpoints — contracts in `02 §3` are binding with fallbacks. Exa + Wispr are OPTIONAL extras, never gate the verdict.
