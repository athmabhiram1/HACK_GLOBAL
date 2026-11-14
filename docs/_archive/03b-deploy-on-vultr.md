# ARCHIVED — starter deploy guide copy (verbatim at time of writing, history only)

Source: `hackglobal-starter/deploy/deploy-on-vultr.md`. See the live file for updates.

1. Create server: Vultr Console → Deploy → Cloud Compute (Shared CPU), near your users, Ubuntu LTS, smallest plan with ≥1GB RAM (BatonGate: use 2GB — nested docker builds OOM on 1GB), name it, Deploy Now. Note IP/Username/Password.
2. `ssh root@YOUR_SERVER_IP`; `curl -fsSL https://get.docker.com | sh`; `apt-get install -y git (+ hadolint for BatonGate)`.
3. `git clone <repo>; cd <app dir>; cp .env.example .env; nano .env` (real keys, server only; never commit).
4. `docker build -t myapp .`; `docker run -d --name myapp --restart unless-stopped --env-file .env -p 80:8000 myapp` (chat-app/research-agent; streamlit uses 8501).
5. `ufw allow 80/tcp` (skip if ufw missing). 6. Open `http://YOUR_SERVER_IP` — this is the Live Demo URL.
Update: `git pull; docker rm -f myapp; docker build; docker run ...`. Debug: `docker ps` / `docker logs myapp`.
Vultr Inference option: `LLM_BASE_URL=https://api.vultrinference.com/v1` + inference key + model. Credits cover the event; add payment or destroy after judging.
