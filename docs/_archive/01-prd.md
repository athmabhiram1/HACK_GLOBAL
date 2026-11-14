# BatonGate — PRD (HackGlobal 2026)

**Title for submission:** BatonGate - 5-Proof Vibe-to-Prod Gate on Vultr
**Theme:** Open Innovation
**Team:** Solo, software-only
**Folder:** `HACK_GLOBAL/` only (this doc is history — build from `docs/PLAN.md` instead)

## 1. Problem
Student vibe-coded apps demo on localhost but fail in prod: missing Dockerfile, hardcoded ports, leaked secrets, vulnerable deps, idle VMs burning $200 credits, README lies. Polaris Y1 expects every freshman to ship a public HTTPS URL, and Vultr requires backend on Vultr Compute plus public URL plus video running on Vultr.

## 2. Goals / Non-goals
Goals: paste repo URL → 0-100 score + SHIP/FIX/BLOCKED + evidence in <3 min on cheapest viable VM; 5 deterministic core gates (+ optional Exa/Wispr extras); one public URL + video-ready logs.
Non-goals: auto-fix push to repo, auto-delete Vultr resources, multi-region, auth/users, payments.

## 3. Functional requirements
Core: build gate (`docker build` + `GET /healthz`), secrets gate (gitleaks SARIF), deps gate (OSV + typosquat + reachability), cost gate (Vultr API read-only + sim), docs gate (diff vs README). Optional: Exa fix-links, Wispr voice input. Verdict from 5 core gates only.

## 4. Stack / cost / risks
See `docs/02-architecture.md` §7 + `docs/PLAN.md` Global Constraints (2GB VM ~$0.65/36h, sandbox flags, never-500 fallbacks). This PRD is superseded by the plan.
