
Started: 2026-10-29 14:05 CET
Stopped: 2026-10-29  CET

Keep it short, ideally 10 to 20 lines. Somewhere in those sections, briefly mention which AI tools you used and one thing you specifically verified, changed or rejected rather than simply accepting generated output.

# 1 setup skeleton:
DB: PostgreSQL 16 (postgres:16-alpine), own database/Dockerfile, schema in database/init/schema.sql (run by postgres entrypoint).
Schema: only cleaned data. assets/policies/claims/fx_rates typed (NUMERIC money, DATE dates, fx month = first of month) with PK/FK and CHECKs (currency, status, peril, region, asset_type, expiry > inception, premium/sum insured > 0, reserve >= 0); excluded_rows (file, row id, reason) for the data-quality report.
Data policy: see # 2.
No volume: ephemeral DB, fresh every start.
Postgres published on 127.0.0.1:5432 only (for local tests).
Credentials: .env (already gitignored, line 131) + committed .env.example.
Backend: Python 3.12, uv + pyproject + uv.lock, SQLAlchemy Core + psycopg, port 8000.
Data loading happens in core on startup (see # 2).
/health runs SELECT 1; test hits a real DB.
Tests run locally via uv;
Trivial choices (Claude): table names as the CSVs, layout core/app + core/tests, DATABASE_URL read via os.environ and `uv run --env-file ../.env` (no dotenv dependency).

# 2 data loading (core/app/load.py, run by the FastAPI lifespan):
Mechanics: pandas; CSVs bind-mounted read-only (./data:/data:ro, DATA_DIR); every startup TRUNCATEs all six tables and reloads in one transaction, so a core restart is safe.
Excluded (excluded_rows, one entry per row, reasons joined with "; "): orphan claims 260. Generic rules that hit nothing today: duplicate id -> keep first in file order, exclude the rest; any value failing a schema type/CHECK -> excluded with reason; children of an excluded parent cascade as orphans.
Kept but flagged (flagged_rows, one entry per issue; reason prefix before ":" groups them):
- fixed peril (trim + lowercase): 1,321 policies (610 had whitespace, 711 only case).
- fixed loss_date / reported_date: DD-MM-YYYY -> stored as DATE (YYYY-MM-DD), original value kept in the reason: 550 / 548 claims. Read as DD-MM: no value has a 2nd part > 12, 690 have a 1st part > 12.
- term overlaps: later policy on the same asset+peril whose term overlaps an earlier one by > 7 days (earlier expiry - later inception): 1,928. Another 84 pairs overlap by <= 7 days (renewal slack) and are not flagged. All policies kept.
- loss_date before policy inception: 310 claims, kept on the stated policy (77 had exactly one other covering policy on the same asset+peril, 6 had two, 227 none).
- negative paid_amount: 262 settled claims, kept as-is (lowers incurred loss).
- settled with reserve_amount > 0: 721, loaded raw; the endpoint will use paid only for settled claims, per BRIEF.
Not flagged: claim currency != policy currency (859), expected per BRIEF.
Independent check: tests/test_load.py recounts every table, exclusion and flag from the raw CSVs with stdlib csv and compares to the DB.
Trivial choices (Claude): clean() (pure, testable) + load() (DB) split; summary logged to uvicorn's logger; validation of unexpected rows covered by a tiny tmp_path CSV test.

# **What I built**

# **What I deliberately did not build, and why**

# **What I would do first with another day**