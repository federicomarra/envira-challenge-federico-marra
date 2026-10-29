from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.db import engine

router = APIRouter()

# Rules in DECISIONS.md: premium at its inception-month rate, claims at their reported-month rate;
# negative paid_amount is a sign error (abs); settled = paid, open = paid + reserve; only open/settled claims count.
# Every policy and every counting claim in DKK, tagged with portfolio and peril; both endpoints aggregate these.
IN_DKK = """
WITH pol AS (
    SELECT a.portfolio_id, p.policy_id, p.peril, p.annual_premium * fx.rate_dkk_per_unit AS premium_dkk
    FROM policies p
    JOIN assets a USING (asset_id)
    JOIN fx_rates fx ON fx.currency = p.currency AND fx.month = date_trunc('month', p.inception_date)
), clm AS (
    SELECT pol.portfolio_id, pol.peril,
           (abs(c.paid_amount) + CASE WHEN c.status = 'open' THEN c.reserve_amount ELSE 0 END) * fx.rate_dkk_per_unit AS incurred_dkk
    FROM claims c
    JOIN pol USING (policy_id)
    JOIN fx_rates fx ON fx.currency = c.currency AND fx.month = date_trunc('month', c.reported_date)
    WHERE c.status IN ('open', 'settled')
)
"""

# Policies and claims are grouped separately before joining, so claims can't multiply premium.
LOSS_EXPERIENCE = text(IN_DKK + """
SELECT p.peril,
       p.policy_count,
       round(p.premium, 2) AS earned_premium_dkk,
       round(coalesce(c.incurred, 0), 2) AS incurred_loss_dkk,
       round(coalesce(c.incurred, 0) / p.premium, 4) AS loss_ratio,
       coalesce(c.claim_count, 0) AS claim_count,
       round(c.largest, 2) AS largest_claim_dkk
FROM (SELECT peril, count(*) AS policy_count, sum(premium_dkk) AS premium
      FROM pol WHERE portfolio_id = :portfolio_id GROUP BY peril) p
LEFT JOIN (SELECT peril, sum(incurred_dkk) AS incurred, count(*) AS claim_count, max(incurred_dkk) AS largest
           FROM clm WHERE portfolio_id = :portfolio_id GROUP BY peril) c USING (peril)
ORDER BY p.peril
""")

# Same figures per portfolio. ROLLUP adds one more row with portfolio_id NULL: the whole book, exact in SQL.
PORTFOLIOS = text(IN_DKK + """
SELECT p.portfolio_id,
       p.policy_count,
       round(p.premium, 2) AS earned_premium_dkk,
       round(coalesce(c.incurred, 0), 2) AS incurred_loss_dkk,
       round(coalesce(c.incurred, 0) / p.premium, 4) AS loss_ratio,
       coalesce(c.claim_count, 0) AS claim_count,
       round(c.largest, 2) AS largest_claim_dkk,
       round(coalesce(c.incurred, 0) - p.premium, 2) AS dkk_lost
FROM (SELECT portfolio_id, count(*) AS policy_count, sum(premium_dkk) AS premium FROM pol GROUP BY ROLLUP (portfolio_id)) p
LEFT JOIN (SELECT portfolio_id, sum(incurred_dkk) AS incurred, count(*) AS claim_count, max(incurred_dkk) AS largest
           FROM clm GROUP BY ROLLUP (portfolio_id)) c ON c.portfolio_id IS NOT DISTINCT FROM p.portfolio_id
""")


@router.get("/portfolios/loss-experience")
def portfolios_loss_experience(
    order: Annotated[Literal["loss_ratio", "dkk_lost", "largest_claim"], Query(
        description="Ranking, always worst first (descending), ties by portfolio_id. "
                    "`loss_ratio` (default): incurred / earned premium. "
                    "`dkk_lost`: incurred − earned premium in DKK. "
                    "`largest_claim`: largest single claim in DKK.")] = "loss_ratio",
):
    """Compare all portfolios: totals per portfolio, ranked worst first, plus `book` (the whole book) as a benchmark.

    Same figures as the per-portfolio endpoint, summed over perils, plus `dkk_lost` = incurred − earned premium
    (positive = losing money; no expenses, so not an underwriting result). All money in DKK.
    """
    with engine.connect() as conn:
        rows = conn.execute(PORTFOLIOS).mappings().all()
    book = next(dict(r) for r in rows if r["portfolio_id"] is None)
    del book["portfolio_id"]
    key = "largest_claim_dkk" if order == "largest_claim" else order
    portfolios = sorted((r for r in rows if r["portfolio_id"] is not None),
                        key=lambda r: (-(r[key] or 0), r["portfolio_id"]))
    return {"order": order, "book": book, "portfolios": portfolios}


@router.get("/portfolios/{portfolio_id}/loss-experience")
def loss_experience(portfolio_id: str):
    with engine.connect() as conn:
        perils = conn.execute(LOSS_EXPERIENCE, {"portfolio_id": portfolio_id}).mappings().all()
    if not perils:
        raise HTTPException(404, f"unknown portfolio {portfolio_id}")
    return {"portfolio_id": portfolio_id, "perils": perils}
