Started: 2026-10-29 14:05 CET
Stopped: 2026-10-29 16:15 CET

10 mins delay for medical issues with my diabetes

# **What I built**
I started from an empty repo
- FastAPI + Postgres 16, started with `docker compose up` on port 8000. The CSVs are cleaned and loaded on every startup. This covers backlog items 1–4 and 6–8.
- `GET /portfolios/{id}/loss-experience` per peril. `GET /portfolios/loss-experience` ranks portfolios by loss ratio, worst first, because it doesn't depend on portfolio size; `?order=dkk_lost|largest_claim` are the alternatives, and a `book` row gives a benchmark. Both endpoints share one SQL CTE that holds the FX and incurred rules.
- FX: premium at the month-end rate of its inception month, claims at the rate of their reported month. EUR only moves 7.43–7.46, so this changes the book LR by < 0.01%.
- Data quality: 260 orphan claims excluded. 5,640 issues kept but flagged: peril case/whitespace, DD-MM-YYYY dates, term overlaps > 7 days, loss before inception, settled with reserve > 0, negative paid. `GET /report` counts them and can be filtered by underwriting year, region and asset type.
- The judgement call that moves the answer: the 262 negative paid amounts are treated as sign errors (abs). All are settled with reserve 0, normal-sized, and have no matching positive payment, so they don't look like recoveries. Book LR is 0.80 with abs and 0.70 without.
- AI: Claude Code, steered by the committed CLAUDE.md, plus the ponytail plugin for an over-engineering pass. I didn't take its numbers on trust: the tests recompute every portfolio × peril from the raw CSVs with stdlib csv and share no service code, and I hand-computed PF-01 before the endpoint existed. I rejected its suggestion to replace database/Dockerfile with a compose volume mount.

# **What I deliberately did not build, and why**
- The page for non-technical users (item 5): I spent the time verifying the numbers. Swagger at /docs covers the walkthrough.
- Filters on the loss endpoints: I added them to /report only, so the verified loss endpoints stayed unchanged.
- Re-matching the 310 claims dated before policy inception: matching is a business call, and only 77 had one obvious alternative policy. They stay on their stated policy and are flagged.
- Credibility weighting in the ranking: all 12 portfolios are a similar size (6.1–7.4M DKK premium, 880–1,070 policies).
- DB volume or cache: the DB is rebuilt from the CSVs on every start, and 12 portfolios don't need a cache.

# **What I would do first with another day**
- Check with the data owner that the negative paid amounts really are sign errors. That decision alone moves PF-01 subsidence from an LR of 0.14 to 0.85.
- Add the same filters to both loss endpoints, reusing /report's POLICY_MATCH SQL.
- Build the portfolio picker page on top of the existing endpoints.