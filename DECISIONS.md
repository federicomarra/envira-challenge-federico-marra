
Started: 2026-10-29 14:05 CET
Stopped: 2026-10-29  CET

Keep it short, ideally 10 to 20 lines. Somewhere in those sections, briefly mention which AI tools you used and one thing you specifically verified, changed or rejected rather than simply accepting generated output.

#1 setup skeleton:
DB: PostgreSQL 16 (postgres:16-alpine), own database/Dockerfile, schema in database/init/schema.sql (run by postgres entrypoint).
Schema: only cleaned data. assets/policies/claims/fx_rates typed (NUMERIC money, DATE dates, fx month = first of month) with PK/FK and CHECKs (currency, status, peril, region, asset_type, expiry > inception, premium/sum insured > 0, reserve >= 0); excluded_rows (file, row id, reason) for the data-quality report.
Data policy so far: orphan claims (260) excluded and counted; DD-MM-YYYY claim dates (~575) parsed; peril trimmed+lowercased; negative paid_amount (262) kept as-is, policy not decided yet.
No volume: ephemeral DB, fresh every start.
Postgres published on 127.0.0.1:5432 only (for local tests).
Credentials: .env (already gitignored, line 131) + committed .env.example.
Backend: Python 3.12, uv + pyproject + uv.lock, SQLAlchemy Core + psycopg, port 8000.
Data loading (later step) will happen in backend on startup.
/health runs SELECT 1; test hits a real DB.
Tests run locally via uv;
Trivial choices (Claude): table names as the CSVs, layout core/app + core/tests, DATABASE_URL read via os.environ and `uv run --env-file ../.env` (no dotenv dependency).

# **What I built**

# **What I deliberately did not build, and why**

# **What I would do first with another day**