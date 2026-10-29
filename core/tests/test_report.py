import csv
import os
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
        with_ids = client.get("/report", params={"excludedIDs": "true"}).json()

    # Recount from the raw files with stdlib csv only.
    policies, claims = rows("policies.csv"), rows("claims.csv")
    policy_ids = {p["policy_id"] for p in policies}
    orphans = {c["claim_id"] for c in claims if c["policy_id"] not in policy_ids}

    assert report["loaded"]["claims"] == len(claims) - len(orphans)
    assert report["excluded"] == [{"source_file": "claims.csv", "reason": "orphan policy_id", "count": len(orphans)}]
    assert set(with_ids["excluded"][0]["row_ids"]) == orphans
    assert len(with_ids["excluded"][0]["row_ids"]) == len(orphans)

    flagged = {f["issue"]: f["count"] for f in report["flagged"]}
    assert set(flagged) == {"fixed peril", "term overlaps", "fixed loss_date", "fixed reported_date",
                            "loss_date before policy inception", "negative paid_amount", "settled with reserve_amount > 0"}
    assert flagged["fixed peril"] == sum(p["peril"] != p["peril"].strip().lower() for p in policies)
