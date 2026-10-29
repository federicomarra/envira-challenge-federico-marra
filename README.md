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

Rows that were left out go to `excluded_rows`. Rows that were kept but fixed or look suspicious go to `flagged_rows`. The rules are in DECISIONS.md; `GET /report` (below) summarizes both.

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

Compare all portfolios. Each row has the same figures summed over perils, plus `dkk_lost` = incurred − earned premium (positive means losing money). `book` is the whole book, there to benchmark against:

```bash
curl -s localhost:8000/portfolios/loss-experience
```

```text
{"order":"loss_ratio","book":{"policy_count":11560,"earned_premium_dkk":79771396.34,"incurred_loss_dkk":64093566.22,
  "loss_ratio":0.8035,"claim_count":3676,"largest_claim_dkk":455259.37,"dkk_lost":-15677830.12},
 "portfolios":[{"portfolio_id":"PF-03","policy_count":958,"earned_premium_dkk":6586893.07,"incurred_loss_dkk":6849631.97,
  "loss_ratio":1.0399,"claim_count":336,"largest_claim_dkk":455259.37,"dkk_lost":262738.91}, ...]}
```

Ranking is worst first (descending), with ties broken by `portfolio_id`. Pick it with `?order=`. Any other value returns 422:

| `order` | sorts by |
|---|---|
| `loss_ratio` (default) | incurred / earned premium |
| `dkk_lost` | incurred − earned premium, in DKK |
| `largest_claim` | largest single claim, in DKK |

```bash
curl -s "localhost:8000/portfolios/loss-experience?order=dkk_lost"
```

```bash
curl -s "localhost:8000/portfolios/loss-experience?order=largest_claim"
```

Data-quality report: what the load excluded (dropped) and flagged (kept, but fixed or suspicious), with counts per reason:

```bash
curl -s localhost:8000/report
```

```text
{"loaded":{"assets":4200,"policies":11560,"claims":4249,"fx_rates":168},
 "excluded":[{"source_file":"claims.csv","reason":"orphan policy_id","count":260}],
 "flagged":[{"source_file":"policies.csv","issue":"term overlaps","count":1928}, ...]}
```

Add `?excluded_ids=true` to also list the excluded row ids:

```bash
curl -s "localhost:8000/report?excluded_ids=true"
```

Interactive API docs, where the `order` options appear as a dropdown: http://localhost:8000/docs

Inspect the database (published on 127.0.0.1:5432 only):

```bash
docker compose exec db psql -U envira -d envira -c '\dt'
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
│   │   ├── db.py                  # SQLAlchemy engine (DATABASE_URL)
│   │   ├── load.py                # CSV cleaning + load into Postgres on startup
│   │   ├── loss_experience.py     # SQL + GET /portfolios/{id}/loss-experience, GET /portfolios/loss-experience
│   │   ├── main.py                # App, startup load, GET /health, mounts the loss_experience and report routers
│   │   └── report.py              # GET /report: excluded / flagged counts per reason (+ excluded ids on request)
│   ├── tests/
│   │   ├── test_health.py         # pytest, against the real DB
│   │   ├── test_load.py           # DB vs independent stdlib-csv recount; bad-row exclusion
│   │   ├── test_loss_experience.py # both endpoints vs independent stdlib-csv recompute (every portfolio x peril, every portfolio, book, ranking)
│   │   └── test_report.py         # GET /report vs independent stdlib-csv recount (orphan claims + ids, peril fixes)
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
