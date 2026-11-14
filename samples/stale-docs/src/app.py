"""Stale-docs fixture: code serves GET /api/healthz; README documents GET /health."""
from fastapi import FastAPI

app = FastAPI()


@app.get("/api/healthz")
def healthz():
    return {"status": "ok"}
