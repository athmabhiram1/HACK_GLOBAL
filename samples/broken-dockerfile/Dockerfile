# BatonGate broken-dockerfile fixture — intentionally broken per parsers (Task 2).
# 1. Missing EXPOSE (no EXPOSE instruction at all).
# 2. `latest` tag (DL3007) — must be flagged by hadolint AST / regex fallback.
# 3. Hardcoded localhost:3000 reference lives in compose.yaml + .env (parsed by parsers).
FROM python:latest
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["python", "app.py"]
