# Starter Guide — fork hackglobal-starter into BatonGate

Source: `hackglobal-starter/` (MIT). Read-first copies of the starter README + deploy guide live in `docs/_archive/03a-starter-readme.md`, `03b-deploy-on-vultr.md` (verbatim at time of writing).

## Which template
Fork `templates/chat-app` only. It already gives FastAPI + `GET /` static + `GET /health {status:ok,model}` + `POST /api/chat` + `Dockerfile python:3.12-slim EXPOSE 8000` + `requirements fastapi/uvicorn/openai/python-dotenv` + `.env LLM_BASE_URL/API_KEY/MODEL`.
Delete `research-agent` and `streamlit-demo` from your repo copy (keep this reference only).

## Keep / change
Keep: `main.py` structure (load_dotenv, env defaults, FileResponse for `/`, HTTPException 500/502 pattern, last-20-messages trim), Dockerfile layers, `.env.example` never-commit rule, `static/index.html` fetch-POST-error pattern.
Change: rename `GET /health` → keep plus add `GET /api/healthz`; add `POST /api/gate` + `GET /api/jobs/{id}`; extend `requirements.txt` with `httpx>=0.27` (OSV/Vultr calls), `exa-py`, `Levenshtein`, `pytest` + test deps; `.env` add `VULTR_API_KEY=` (empty, in-memory only), `DEMO_MODE=0`, `GITLEAKS_VERSION=8.18.4`. Optional only: `EXA_API_KEY=`, `WISPR_API_KEY=`.

## Deploy (starter flow, pinned)
Smallest plan ≥2GB RAM (BatonGate runs nested docker builds — 1GB OOMs), Ubuntu LTS, `curl -fsSL https://get.docker.com | sh`, `git clone <your-public-repo>`, `cp .env.example .env` + fill on server, `docker build -t baton .`, `docker run -d --restart unless-stopped --env-file .env -p 80:8000 baton`, `ufw allow 80/tcp`, open `http://IP` in private window. Vultr Inference: `LLM_BASE_URL=https://api.vultrinference.com/v1`. Update: `git pull; docker rm -f baton; docker build; docker run`.

## What the starter does NOT give you
Gates, verdict, SARIF, OSV batch, sandbox flags, queue, report JSON, dashboard cards — all in `02-architecture.md` §3-6. Do not invent starter behavior; the starter is skeleton only.
