import csv
import os
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

DATA = Path(os.environ["DATA_DIR"])


def rows(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_report_matches_raw_csvs():
    with TestClient(app) as client:  # runs the lifespan, which loads the CSVs
        report = client.get("/report").json()
        with_ids = client.get("/report", params={"excluded_ids": "true"}).json()

    # Recount from the raw files with stdlib csv only.
    policies, claims = rows("policies.csv"), rows("claims.csv")
    policy_ids = {p["policy_id"] for p in policies}
    orphans = {c["claim_id"] for c in claims if c["policy_id"] not in policy_ids}

    assert report["loaded"]["claims"] == len(claims) - len(orphans)
    assert report["excluded"] == [{"source_file": "claims.csv", "reason": "orphan policy_id", "count": len(orphans)}]
    assert set(with_ids["excluded"][0]["row_ids"]) == orphans

    flagged = {f["issue"]: f["count"] for f in report["flagged"]}
    assert set(flagged) == {"fixed peril", "term overlaps", "fixed loss_date", "fixed reported_date",
                            "loss_date before policy inception", "negative paid_amount", "settled with reserve_amount > 0"}


def test_report_filters_match_raw_csvs():
    assets, policies, claims = rows("assets.csv"), rows("policies.csv"), rows("claims.csv")
    values = {"underwriting_year": sorted({p["inception_date"][:4] for p in policies}),
              "region": sorted({a["region"] for a in assets}),
              "asset_type": sorted({a["asset_type"] for a in assets})}
    with TestClient(app) as client:  # runs the lifespan, which loads the CSVs
        get = lambda **filters: client.get("/report", params=filters).json()
        whole = get()
        sliced = get(underwriting_year=2023, region="Hovedstaden", asset_type="residential")
        slices = {f: [get(**{f: v}) for v in vs] for f, vs in values.items()}
        assert client.get("/report", params={"region": "Mars"}).status_code == 422

    # Recount one slice from the raw files with stdlib csv only.
    in_assets = {a["asset_id"] for a in assets if (a["region"], a["asset_type"]) == ("Hovedstaden", "residential")}
    in_policies = [p for p in policies if p["asset_id"] in in_assets and p["inception_date"][:4] == "2023"]
    in_claims = [c for c in claims if c["policy_id"] in {p["policy_id"] for p in in_policies}]
    assert sliced["loaded"] == {"assets": len(in_assets), "policies": len(in_policies), "claims": len(in_claims),
                                "fx_rates": whole["loaded"]["fx_rates"]}
    flagged = {f["issue"]: f["count"] for f in sliced["flagged"]}
    assert flagged["fixed peril"] == sum(p["peril"] != p["peril"].strip().lower() for p in in_policies)  # policy path
    assert flagged["negative paid_amount"] == sum(float(c["paid_amount"]) < 0 for c in in_claims)  # claim -> policy path
    assert sliced["excluded"] == whole["excluded"]

    # Each filter splits the book: its slices add back up to the unfiltered report, so no flag is lost or double-counted.
    counts = lambda r: Counter({(f["source_file"], f["issue"]): f["count"] for f in r["flagged"]}
                               | {t: r["loaded"][t] for t in ("policies", "claims")})
    for f, reports in slices.items():
        assert sum(map(counts, reports), Counter()) == counts(whole), f
