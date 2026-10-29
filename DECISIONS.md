
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
- negative paid_amount: 262 settled claims, loaded raw; treated as a sign error, so the endpoint uses abs(paid_amount). Why: all are settled with reserve 0, none has a matching positive payment on the same policy, and their sizes look like normal claims (median 6.2k vs 10.2k), so they are not recoveries.
- settled with reserve_amount > 0: 721, loaded raw; the endpoint will use paid only for settled claims, per BRIEF.
Not flagged: claim currency != policy currency (859), expected per BRIEF.
Independent check: tests/test_load.py recounts every table, exclusion and flag from the raw CSVs with stdlib csv and compares to the DB.
Trivial choices (Claude): clean() (pure, testable) + load() (DB) split; summary logged to uvicorn's logger; validation of unexpected rows covered by a tiny tmp_path CSV test.

# 3 GET /portfolios/{portfolio_id}/loss-experience (core/app/main.py, one SQL query):
Per peril: policy_count, earned_premium_dkk (full annual premium), incurred_loss_dkk (settled = paid, open = paid + reserve, withdrawn/declined = 0), loss_ratio (incurred / earned, 4 dp), claim_count and largest_claim_dkk (open + settled only, so incurred / count is average severity). Money rounded to 2 dp. Unknown portfolio -> 404.
FX: premium at the month-end rate of its inception month, claim at the month-end rate of its reported month. EUR only moves 7.43-7.46, so the choice changes the book LR by < 0.01%. EUR labels checked as genuine: the DKK/EUR premium-rate ratio per peril is ~7.45.
Policies and claims are grouped per peril separately and then joined, so a policy's premium is never multiplied by its claim count.
Sensitivity: the negative-paid policy is the one that moves the answer. Book LR is 0.80 with abs vs 0.70 kept as-is. PF-01 subsidence goes 0.85 vs 0.14: its largest claim is CLM-901444, -48,749.17 EUR in source (~363k DKK).
Plausibility: across all 60 portfolio x peril cells, LR ranges 0.25-3.62 (nothing > 10x or ~0). Fire runs highest in every portfolio (up to 3.6); that's a finding, not a data error.
Independent check: tests/test_loss_experience.py recomputes every portfolio x peril from the raw CSVs with stdlib csv (no SQL, no pandas, no app.load) and compares all six fields. PF-01 subsidence is also pinned to hand-checked figures. Curl output for PF-01 matched the hand computation done before the code was written.

# 4 GET /portfolios/loss-experience (core/app/main.py):
Per portfolio: the same six figures summed over perils, plus dkk_lost = incurred − earned premium (positive = losing money). dkk_lost leaves out expenses, so it is not an underwriting result. A top-level `book` (the whole book) is there to benchmark against.
Ranking (my choice): loss ratio, worst first. It doesn't depend on portfolio size, and the brief defines it. All 12 portfolios are a similar size (6.1–7.4M DKK premium, 880–1,070 policies, 284–336 claims), so credibility weighting wasn't needed. ?order=dkk_lost (DKK lost, most first) and ?order=largest_claim (largest single claim, biggest first) are alternatives. All orders sort descending, ties broken by portfolio_id; any other value gets a 422. Options are documented in the README and in Swagger (enum + description).
One query: the pol/clm CTEs (FX + incurred rules) are now shared by both endpoints, so the rules live in one place. GROUP BY ROLLUP (portfolio_id) gives the book row exactly in SQL, so it isn't summed from rounded rows.
Plausibility: portfolio LRs run 0.645–1.040, book 0.803. Only PF-03 is above 1, losing 262,739 DKK. Loss ratio and dkk_lost agree on the order except for a PF-04/PF-06 swap. By largest claim, PF-01 comes second (363k): that's CLM-901444, so it depends on the abs() sign decision in # 3.
Independent check: tests/test_loss_experience.py rolls the stdlib recompute up per portfolio and for the book, compares every field, and checks the order for all three ?order values. The item-1 tests are unchanged and still pass, which shows the CTE refactor didn't move any number. Curl matched the profiling numbers computed from the raw CSVs before the code was written.
Trivial choices (Claude): names IN_DKK, PORTFOLIOS, dkk_lost; sorting in Python (12 rows) rather than a SQL CASE.

# **What I built**

# **What I deliberately did not build, and why**

# **What I would do first with another day**