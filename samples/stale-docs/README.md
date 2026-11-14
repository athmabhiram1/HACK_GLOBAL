# Stale Docs Fixture

Health check:

```sh
curl http://localhost:8000/health
# -> {"status":"ok"}
```

NOTE: the endpoint above is stale — code serves `GET /api/healthz`
(see `src/app.py:6`), so the docs gate must flag this file:line.
