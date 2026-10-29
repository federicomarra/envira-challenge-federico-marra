"""Data-quality report: what the startup load excluded (dropped) or flagged (kept, but fixed or suspicious), and why."""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine

router = APIRouter()


@router.get("/report")
def report(excluded_ids: Annotated[bool, Query(alias="excludedIDs", description="List the excluded row ids too.")] = False):
    """Counts per reason of excluded rows (dropped on load) and flagged rows (kept, grouped by issue). Rules in DECISIONS.md."""
    with engine.connect() as conn:
        q = lambda sql: [dict(r) for r in conn.execute(text(sql)).mappings()]
        loaded = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in ("assets", "policies", "claims", "fx_rates")}
        excluded = q("SELECT source_file, reason, count(*) AS count"
                     + (", array_agg(row_id ORDER BY row_id) AS row_ids" if excluded_ids else "")
                     + " FROM excluded_rows GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2")
        flagged = q("SELECT source_file, split_part(reason, ':', 1) AS issue, count(*) AS count"
                    " FROM flagged_rows GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2")
    return {"loaded": loaded, "excluded": excluded, "flagged": flagged}
