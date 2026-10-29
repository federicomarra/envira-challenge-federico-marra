import csv
import os
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from itertools import combinations
from pathlib import Path

from sqlalchemy import text

from app.load import clean, load
from app.main import engine

DATA = Path(os.environ["DATA_DIR"])


def rows(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def any_date(s):
    y, m, d = s.split("-") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else s.split("-")[::-1]
    return date(int(y), int(m), int(d))


def test_load_matches_independent_recount_of_raw_csvs():
    load(engine, DATA)
    load(engine, DATA)  # a restart reloads; it must replace, not duplicate

    # Recount from the raw files with stdlib csv only (no pandas, no app.load logic).
    assets, policies, claims, fx = (rows(n) for n in ("assets.csv", "policies.csv", "claims.csv", "fx_rates.csv"))
    policy = {p["policy_id"]: p for p in policies}
    kept = [c for c in claims if c["policy_id"] in policy]
    terms = defaultdict(list)
    for p in policies:
        terms[p["asset_id"], p["peril"].strip().lower()].append((p["inception_date"], p["expiry_date"]))
    expected_flags = {
        "fixed peril": sum(p["peril"] != p["peril"].strip().lower() for p in policies),
        "term overlaps": sum((date.fromisoformat(e1) - date.fromisoformat(i2)).days > 7
                             for ts in terms.values() for (i1, e1), (i2, e2) in combinations(sorted(ts), 2)),
        "fixed loss_date": sum(c["loss_date"][4] != "-" for c in kept),
        "fixed reported_date": sum(c["reported_date"][4] != "-" for c in kept),
        "loss_date before policy inception": sum(
            any_date(c["loss_date"]) < date.fromisoformat(policy[c["policy_id"]]["inception_date"]) for c in kept),
        "negative paid_amount": sum(float(c["paid_amount"]) < 0 for c in kept),
        "settled with reserve_amount > 0": sum(c["status"] == "settled" and float(c["reserve_amount"]) > 0 for c in kept),
    }

    with engine.connect() as conn:
        q = lambda sql, **params: conn.execute(text(sql), params)
        counts = [q(f"SELECT count(*) FROM {t}").scalar() for t in ("assets", "policies", "claims", "fx_rates")]
        assert counts == [len(assets), len(policies), len(kept), len(fx)]
        assert dict(q("SELECT reason, count(*) FROM excluded_rows GROUP BY 1").all()) == {"orphan policy_id": len(claims) - len(kept)}
        assert dict(q("SELECT split_part(reason, ':', 1), count(*) FROM flagged_rows GROUP BY 1").all()) == expected_flags

        assert q("SELECT loss_date, paid_amount FROM claims WHERE claim_id = 'CLM-900320'").one() == (date(2024, 8, 24), Decimal("-6725.27"))
        assert q("SELECT reason FROM flagged_rows WHERE row_id = 'CLM-900320' AND reason LIKE 'fixed loss_date%'").scalar() \
            == "fixed loss_date: '24-08-2024' -> 2024-08-24"
        raw_fire = next(p["policy_id"] for p in policies if p["peril"] == " fire")
        assert q("SELECT peril FROM policies WHERE policy_id = :id", id=raw_fire).scalar() == "fire"


def test_clean_excludes_unexpected_rows(tmp_path):
    files = {
        "assets.csv": ["asset_id,portfolio_id,region,asset_type,construction_year,sum_insured_dkk",
                       "AST-1,PF-01,Syddanmark,residential,1990,1000000.0",
                       "AST-1,PF-02,Syddanmark,residential,1990,1000000.0"],
        "policies.csv": ["policy_id,asset_id,peril,inception_date,expiry_date,annual_premium,currency",
                         "POL-1,AST-1,fire,2023-01-01,2023-12-31,100.0,DKK",
                         "POL-2,AST-1,fire,2023-01-01,2023-12-31,100.0,USD",
                         "POL-3,AST-1,fire,2023-13-01,2023-12-31,100.0,DKK"],
        "claims.csv": ["claim_id,policy_id,loss_date,reported_date,paid_amount,reserve_amount,currency,status",
                       "CLM-1,POL-1,2023-05-01,2023-05-10,10.0,0.0,DKK,settled",
                       "CLM-2,POL-2,2023-05-01,2023-05-10,10.0,0.0,DKK,settled",
                       "CLM-3,POL-9,31-02-2023,2023-05-10,10.0,0.0,DKK,settled"],
        "fx_rates.csv": ["month,currency,rate_dkk_per_unit", "2023-01,EUR,7.45"],
    }
    for name, lines in files.items():
        (tmp_path / name).write_text("\n".join(lines) + "\n")

    tables, excluded, _ = clean(tmp_path)

    assert set(excluded.itertuples(index=False, name=None)) == {
        ("assets.csv", "AST-1", "duplicate id"),
        ("policies.csv", "POL-2", "unknown currency"),
        ("policies.csv", "POL-3", "unparseable inception_date"),
        ("claims.csv", "CLM-2", "orphan policy_id"),
        ("claims.csv", "CLM-3", "orphan policy_id; unparseable loss_date"),
    }
    assert tables["assets"]["portfolio_id"].tolist() == ["PF-01"]  # first copy kept
    assert tables["claims"]["claim_id"].tolist() == ["CLM-1"]
