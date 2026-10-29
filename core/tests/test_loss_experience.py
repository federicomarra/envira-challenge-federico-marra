import csv
import os
from collections import defaultdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import approx

from app.main import app

DATA = Path(os.environ["DATA_DIR"])


def rows(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def recompute():
    """Every portfolio x peril straight from the raw CSVs, stdlib only (no SQL, no pandas, no app.load)."""
    fx = {(r["month"], r["currency"]): float(r["rate_dkk_per_unit"]) for r in rows("fx_rates.csv")}
    portfolio = {a["asset_id"]: a["portfolio_id"] for a in rows("assets.csv")}
    policies = {p["policy_id"]: p for p in rows("policies.csv")}
    key = lambda p: (portfolio[p["asset_id"]], p["peril"].strip().lower())
    out = defaultdict(lambda: {"policy_count": 0, "earned_premium_dkk": 0.0, "incurred_loss_dkk": 0.0,
                               "claim_count": 0, "largest_claim_dkk": None})
    for p in policies.values():
        e = out[key(p)]
        e["policy_count"] += 1
        e["earned_premium_dkk"] += float(p["annual_premium"]) * fx[p["inception_date"][:7], p["currency"]]
    for c in rows("claims.csv"):
        if c["policy_id"] not in policies or c["status"] not in ("open", "settled"):
            continue
        reported = c["reported_date"] if c["reported_date"][4] == "-" else "-".join(c["reported_date"].split("-")[::-1])
        paid = abs(float(c["paid_amount"])) + (float(c["reserve_amount"]) if c["status"] == "open" else 0)
        dkk = paid * fx[reported[:7], c["currency"]]
        e = out[key(policies[c["policy_id"]])]
        e["incurred_loss_dkk"] += dkk
        e["claim_count"] += 1
        e["largest_claim_dkk"] = max(e["largest_claim_dkk"] or 0, dkk)
    return out


def by_portfolio():
    """recompute() rolled up per portfolio, plus the whole book under key None."""
    out = defaultdict(lambda: {"policy_count": 0, "earned_premium_dkk": 0.0, "incurred_loss_dkk": 0.0,
                               "claim_count": 0, "largest_claim_dkk": 0.0})
    for (pf, _), e in recompute().items():
        for t in (out[pf], out[None]):
            for field in ("policy_count", "earned_premium_dkk", "incurred_loss_dkk", "claim_count"):
                t[field] += e[field]
            t["largest_claim_dkk"] = max(t["largest_claim_dkk"], e["largest_claim_dkk"] or 0)
    for t in out.values():
        t["loss_ratio"] = t["incurred_loss_dkk"] / t["earned_premium_dkk"]
        t["dkk_lost"] = t["incurred_loss_dkk"] - t["earned_premium_dkk"]
    return out


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs the lifespan, which loads the CSVs
        yield c


def test_every_portfolio_matches_independent_recompute(client):
    want = recompute()
    got = {}
    for pf in sorted({pf for pf, _ in want}):
        r = client.get(f"/portfolios/{pf}/loss-experience")
        assert r.status_code == 200
        for row in r.json()["perils"]:
            got[pf, row.pop("peril")] = row

    assert got.keys() == want.keys()
    for k, w in want.items():
        g = got[k]
        assert (g["policy_count"], g["claim_count"]) == (w["policy_count"], w["claim_count"]), k
        for field in ("earned_premium_dkk", "incurred_loss_dkk", "largest_claim_dkk"):
            assert g[field] == approx(w[field], abs=0.01), (k, field)
        assert g["loss_ratio"] == approx(w["incurred_loss_dkk"] / w["earned_premium_dkk"], abs=1e-4), k


def test_pf01_subsidence_pinned(client):
    # Hand-checked. Largest claim is CLM-901444, -48,749.17 EUR in source: the sign flip moves LR from 0.14 to 0.85.
    perils = {p.pop("peril"): p for p in client.get("/portfolios/PF-01/loss-experience").json()["perils"]}
    assert perils["subsidence"] == {"policy_count": 169, "earned_premium_dkk": 1065094.94, "incurred_loss_dkk": 902520.02,
                                    "loss_ratio": 0.8474, "claim_count": 19, "largest_claim_dkk": 363195.94}


def test_unknown_portfolio_is_404(client):
    assert client.get("/portfolios/PF-99/loss-experience").status_code == 404


def test_all_portfolios_match_independent_recompute(client):
    want = by_portfolio()
    r = client.get("/portfolios/loss-experience").json()
    got = {p.pop("portfolio_id"): p for p in r["portfolios"]} | {None: r["book"]}

    assert got.keys() == want.keys()
    for k, w in want.items():
        g = got[k]
        assert (g["policy_count"], g["claim_count"]) == (w["policy_count"], w["claim_count"]), k
        for field in ("earned_premium_dkk", "incurred_loss_dkk", "largest_claim_dkk", "dkk_lost"):
            assert g[field] == approx(w[field], abs=0.01), (k, field)
        assert g["loss_ratio"] == approx(w["loss_ratio"], abs=1e-4), k


@pytest.mark.parametrize("query, order, field", [
    ("", "loss_ratio", "loss_ratio"),
    ("?order=loss_ratio", "loss_ratio", "loss_ratio"),
    ("?order=dkk_lost", "dkk_lost", "dkk_lost"),
    ("?order=largest_claim", "largest_claim", "largest_claim_dkk"),
])
def test_all_portfolios_ranked_worst_first(client, query, order, field):
    want = {pf: w for pf, w in by_portfolio().items() if pf is not None}
    r = client.get(f"/portfolios/loss-experience{query}").json()
    assert r["order"] == order
    assert [p["portfolio_id"] for p in r["portfolios"]] == sorted(want, key=lambda pf: (-want[pf][field], pf))


def test_unknown_order_is_422(client):
    assert client.get("/portfolios/loss-experience?order=bogus").status_code == 422
