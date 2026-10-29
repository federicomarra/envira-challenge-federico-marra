# envira-challenge-federico-marra
Envira 2h challenge by Federico Marra

## Setup

Prerequisites: Docker with Compose, and [uv](https://docs.astral.sh/uv/) for running tests locally.

From the repo root:

```bash
unzip envira-loss-data.zip   # creates ./data/*.csv (gitignored, never committed)
cp .env.example .env
```

## Walkthrough

Start Postgres and the API (port 8000):

```bash
docker compose up --build
```

Check the API is up and can reach the database:

```bash
curl -s localhost:8000/health
# {"status":"ok","db":"ok"}
```

Interactive API docs: http://localhost:8000/docs

Inspect the database (published on 127.0.0.1:5432 only):

```bash
docker compose exec db psql -U envira -d envira -c '\dt'
```

Run the tests (needs `db` running):

```bash
cd core && uv run --env-file ../.env pytest -q -W error
```

Stop everything (the database is ephemeral and is recreated on every start):

```bash
docker compose down
```

## Code structure

```text
├── core/                          # FastAPI service
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py                # App, DB engine, GET /health
│   ├── tests/
│   │   └── test_health.py         # pytest, against the real DB
│   ├── pyproject.toml             # Dependencies (uv)
│   ├── uv.lock                    # Locked dependency versions
│   ├── .dockerignore
│   └── Dockerfile                 # python:3.12-slim + uv, runs uvicorn on 8000 port
│
├── database/                      # PostgreSQL 16
│   ├── init/
│   │   └── schema.sql             # Typed tables (PK/FK/CHECKs) + excluded_rows
│   └── Dockerfile                 # postgres:16-alpine with init scripts
│
├── data/                          # CSVs from envira-loss-data.zip (gitignored)
│
├── .env.example                   # DB credentials and local DATABASE_URL; copy to .env
│
└── docker-compose.yml             # db + core services
```
