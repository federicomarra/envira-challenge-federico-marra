# CLAUDE.md

Ask me before deciding on: data-quality policy (exclude, fix or keep a row), claim→policy matching, FX conversion rules, ranking for the all-portfolios endpoint, and any backlog item beyond item 1. For trivial choices (names, file layout), decide and note the choice in DECISIONS.md.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 0. Project context

- Two-hour timebox. Priority: a correct `GET /portfolios/{portfolio_id}/loss-experience`. Everything else in the BRIEF.md backlog is optional.
- Stack: Python + FastAPI, pytest. Data lives in `./data/` (gitignored, never committed).
- Definitions are fixed by BRIEF.md (incurred loss, earned premium = full annual premium, loss ratio in DKK, underwriting year). Do not reinterpret them.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- No database, Docker or cache until the core endpoint is verified correct.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Data Handling

- Profile each CSV before writing logic that depends on it: duplicates, orphan foreign keys, nulls, negative/zero amounts, unknown currencies or statuses, impossible dates.
- Never drop rows silently. Every exclusion is counted, has a reason, and is visible (log, report, or DECISIONS.md).
- FX: state which month-end rate is used (loss date? reported date?) and ask me before choosing.
- Flag commercially implausible figures (e.g. loss ratio > 10x or ~0) instead of passing them through.

## 5. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

Keep at least one independent check that does not reuse the service code: e.g. a script or test that recomputes one portfolio/peril by hand from the raw CSVs and compares.

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 6. Test after executing your tasks
If you've changed something in the repo, run this to check everything works and there are no warnings:
```
pytest -q -W error
```

## 7. Git

Commit after each working step, small and descriptive. Never commit `data/`, the data zip, or secrets.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
