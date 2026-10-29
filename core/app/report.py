"""Data-quality report: what the startup load excluded (dropped) or flagged (kept, but fixed or suspicious), and why."""
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine
from app.load import ASSET_TYPES, REGIONS

router = APIRouter()

# An unset filter matches everything. Assets have no underwriting year; a claim takes its policy's year, region and type.
# CAST(), not ::, because text() doesn't bind :x::int.
ASSET_MATCH = ("(CAST(:region AS text) IS NULL OR a.region = :region)"
               " AND (CAST(:asset_type AS text) IS NULL OR a.asset_type = :asset_type)")
POLICY_MATCH = ("(CAST(:underwriting_year AS int) IS NULL"
                " OR extract(year FROM p.inception_date) = CAST(:underwriting_year AS int)) AND " + ASSET_MATCH)

LOADED = {
    "assets": f"SELECT count(*) FROM assets a WHERE {ASSET_MATCH}",
    "policies": f"SELECT count(*) FROM policies p JOIN assets a USING (asset_id) WHERE {POLICY_MATCH}",
    "claims": f"SELECT count(*) FROM claims JOIN policies p USING (policy_id) JOIN assets a USING (asset_id) WHERE {POLICY_MATCH}",
    "fx_rates": "SELECT count(*) FROM fx_rates",
}

# A policy flag is placed by its policy, a claim flag by claim -> policy -> asset. LEFT joins: unfiltered never loses a row.
FLAGGED = f"""SELECT f.source_file, split_part(f.reason, ':', 1) AS issue, count(*) AS count
FROM flagged_rows f
LEFT JOIN claims c ON f.source_file = 'claims.csv' AND c.claim_id = f.row_id
LEFT JOIN policies p ON p.policy_id = CASE f.source_file WHEN 'policies.csv' THEN f.row_id ELSE c.policy_id END
LEFT JOIN assets a USING (asset_id)
WHERE {POLICY_MATCH}
GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2"""


@router.get("/report")
def report(
    excluded_ids: Annotated[bool, Query(description="List the excluded row ids too.")] = False,
    underwriting_year: Annotated[int | None, Query(description="Policies incepting in this year, and their claims.")] = None,
    region: Literal[tuple(sorted(REGIONS))] | None = None,
    asset_type: Literal[tuple(sorted(ASSET_TYPES))] | None = None,
):
    """Counts per reason of excluded rows (dropped on load) and flagged rows (kept, grouped by issue). Rules in DECISIONS.md.

    Filters narrow `loaded` and `flagged` to that slice of the book (assets ignore `underwriting_year`; fx_rates is always
    the total). `excluded` is always the whole load: excluded rows were never loaded, so nothing places them in a slice.
    """
    params = {"underwriting_year": underwriting_year, "region": region, "asset_type": asset_type}
    with engine.connect() as conn:
        q = lambda sql: [dict(r) for r in conn.execute(text(sql), params).mappings()]
        loaded = {t: conn.execute(text(sql), params).scalar() for t, sql in LOADED.items()}
        excluded = q("SELECT source_file, reason, count(*) AS count"
                     + (", array_agg(row_id ORDER BY row_id) AS row_ids" if excluded_ids else "")
                     + " FROM excluded_rows GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2")
        flagged = q(FLAGGED)
    return {"loaded": loaded, "excluded": excluded, "flagged": flagged}
