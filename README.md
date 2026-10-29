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

On startup core loads `./data/*.csv` into Postgres. It replaces whatever is already there, so a restart is safe. The log shows a summary:

```text
Loaded assets 4200, policies 11560, claims 4249, fx_rates 168; excluded 260 rows; flagged 5640 issues
```

Rows that were left out go to `excluded_rows`. Rows that were kept but fixed or look suspicious go to `flagged_rows`. The rules are in DECISIONS.md.

Check the API is up and can reach the database:

```bash
curl -s localhost:8000/health
# {"status":"ok","db":"ok"}
```

Loss experience for one portfolio (`PF-01` … `PF-12`), per peril, all money in DKK. An unknown portfolio returns 404:

```bash
curl -s localhost:8000/portfolios/PF-01/loss-experience
```

```text
{"portfolio_id":"PF-01","perils":[{"peril":"fire","policy_count":175,"earned_premium_dkk":668775.33,
  "incurred_loss_dkk":398604.73,"loss_ratio":0.596,"claim_count":11,"largest_claim_dkk":67110.75}, ...]}
```

Interactive API docs: http://localhost:8000/docs

Inspect the database (published on 127.0.0.1:5432 only):

```bash
docker compose exec db psql -U envira -d envira -c '\dt'
```

What was excluded or flagged on load:

```bash
docker compose exec db psql -U envira -d envira -c "select reason, count(*) from excluded_rows group by 1"
```

```bash
docker compose exec db psql -U envira -d envira -c "select split_part(reason, ':', 1) as issue, count(*) from flagged_rows group by 1 order by 2 desc"
```

Run the tests (needs `db` running; `test_load.py` reloads the DB from `./data`):

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
│   │   ├── load.py                # CSV cleaning + load into Postgres on startup
│   │   └── main.py                # App, DB engine, startup load, GET /health, GET /portfolios/{id}/loss-experience
│   ├── tests/
│   │   ├── test_health.py         # pytest, against the real DB
│   │   ├── test_load.py           # DB vs independent stdlib-csv recount; bad-row exclusion
│   │   └── test_loss_experience.py # endpoint vs independent stdlib-csv recompute of every portfolio x peril
│   ├── pyproject.toml             # Dependencies (uv)
│   ├── uv.lock                    # Locked dependency versions
│   ├── .dockerignore
│   └── Dockerfile                 # python:3.12-slim + uv, runs uvicorn on 8000 port
│
├── database/                      # PostgreSQL 16
│   ├── init/
│   │   └── schema.sql             # Typed tables (PK/FK/CHECKs) + excluded_rows, flagged_rows
│   └── Dockerfile                 # postgres:16-alpine with init scripts
│
├── data/                          # CSVs from envira-loss-data.zip (gitignored), mounted read-only into core
│
├── .env.example                   # DB credentials, local DATABASE_URL and DATA_DIR; copy to .env
│
└── docker-compose.yml             # db + core services
```
