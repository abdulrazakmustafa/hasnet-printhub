# Hasnet PrintHub

Production-ready starter for a smart self-service printing kiosk platform with:

- Edge devices (Raspberry Pi + CUPS agent)
- Cloud backend (`FastAPI` + `PostgreSQL`)
- Payment orchestration (provider-selectable: Mixx Push API or Snippe)
- Monitoring + alerting foundation

## Repository Layout

```text
hasnet-printhub/
  backend/          # FastAPI backend + DB models + Alembic migrations
  docs/             # Deployment and manual-operation guides
  edge-agent/       # Raspberry Pi monitoring/printing agent docs (code next phase)
```

## Quick Start (Backend)

1. Open terminal in `hasnet-printhub/backend`
2. Create virtual env and install dependencies:
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
   - `pip install -r requirements.txt`
3. Copy env file:
   - `copy .env.example .env`
4. Start PostgreSQL (Docker example):
   - `docker compose up -d`
   - If Docker Desktop shows "Docker Desktop is unable to start", open an **Administrator** PowerShell and run:
     - `wsl --install`
     - `wsl --update`
     - Restart Windows, then start Docker Desktop again.
5. Run migrations:
   - `alembic upgrade head`
6. Run API:
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

Docs: see `docs/manual-steps.md` for all manual setup actions (DNS, SSL, SMTP, payment provider credentials, and Raspberry Pi prep).

For intranet-first rollout where customer flow runs fully on Pi, use:
- `docs/pi-local-hosting-runbook.md`
