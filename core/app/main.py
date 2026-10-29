import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text

from app.load import load

engine = create_engine(os.environ["DATABASE_URL"])


@asynccontextmanager
async def lifespan(app):
    load(engine, os.environ["DATA_DIR"])
    yield


app = FastAPI(title="Envira loss experience", lifespan=lifespan)

# Rules in DECISIONS.md: premium at its inception-month rate, claims at their reported-month rate;
# negative paid_amount is a sign error (abs); settled = paid, open = paid + reserve; only open/settled claims count.
# Policies and claims are grouped per peril separately before joining, so claims can't multiply premium.
LOSS_EXPERIENCE = text("""
WITH pol AS (
    SELECT p.policy_id, p.peril, p.annual_premium * fx.rate_dkk_per_unit AS premium_dkk
    FROM policies p
    JOIN assets a USING (asset_id)
    JOIN fx_rates fx ON fx.currency = p.currency AND fx.month = date_trunc('month', p.inception_date)
    WHERE a.portfolio_id = :portfolio_id
), clm AS (
    SELECT pol.peril,
           (abs(c.paid_amount) + CASE WHEN c.status = 'open' THEN c.reserve_amount ELSE 0 END) * fx.rate_dkk_per_unit AS incurred_dkk
    FROM claims c
    JOIN pol USING (policy_id)
    JOIN fx_rates fx ON fx.currency = c.currency AND fx.month = date_trunc('month', c.reported_date)
    WHERE c.status IN ('open', 'settled')
)
SELECT p.peril,
       p.policy_count,
       round(p.premium, 2) AS earned_premium_dkk,
       round(coalesce(c.incurred, 0), 2) AS incurred_loss_dkk,
       round(coalesce(c.incurred, 0) / p.premium, 4) AS loss_ratio,
       coalesce(c.claim_count, 0) AS claim_count,
       round(c.largest, 2) AS largest_claim_dkk
FROM (SELECT peril, count(*) AS policy_count, sum(premium_dkk) AS premium FROM pol GROUP BY peril) p
LEFT JOIN (SELECT peril, sum(incurred_dkk) AS incurred, count(*) AS claim_count, max(incurred_dkk) AS largest
           FROM clm GROUP BY peril) c USING (peril)
ORDER BY p.peril
""")


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}


@app.get("/portfolios/{portfolio_id}/loss-experience")
def loss_experience(portfolio_id: str):
    with engine.connect() as conn:
        perils = conn.execute(LOSS_EXPERIENCE, {"portfolio_id": portfolio_id}).mappings().all()
    if not perils:
        raise HTTPException(404, f"unknown portfolio {portfolio_id}")
    return {"portfolio_id": portfolio_id, "perils": perils}
