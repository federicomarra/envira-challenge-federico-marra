"""Load the CSVs into Postgres on startup. The data-quality rules are explained in DECISIONS.md."""
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text

log = logging.getLogger("uvicorn.error")

# Same values as the CHECKs in database/init/schema.sql.
REGIONS = {"Hovedstaden", "Midtjylland", "Nordjylland", "Sjaelland", "Syddanmark"}
ASSET_TYPES = {"agricultural", "commercial", "industrial", "public", "residential"}
PERILS = {"fire", "flood", "hail", "storm", "subsidence"}
CURRENCIES = {"DKK", "EUR"}
STATUSES = {"open", "settled", "withdrawn", "declined"}
OVERLAP_FLAG_DAYS = 7  # shorter overlaps on the same asset+peril are treated as renewal slack


def _rows(file, ids, reasons):
    return pd.DataFrame({"source_file": file, "row_id": ids, "reason": reasons})


def _exclude(df, file, ids, checks):
    """Return (kept rows, excluded_rows entries). Later copies of an id are excluded; a row failing several checks gets one entry."""
    why = pd.Series("", index=df.index)
    for bad, reason in [(ids.duplicated(), "duplicate id"), *checks]:
        why[bad] += "; " + reason
    bad = why != ""
    return df[~bad], _rows(file, ids[bad], why[bad].str[2:])


def _number(s):
    return pd.to_numeric(s, errors="coerce")


def _date(s, fmt="%Y-%m-%d"):
    return pd.to_datetime(s, format=fmt, errors="coerce")


def clean(data_dir):
    """Validate and fix the raw CSVs. Returns ({table: rows to insert}, excluded_rows, flagged_rows)."""
    read = lambda name: pd.read_csv(Path(data_dir) / name, dtype=str, keep_default_na=False)
    excluded, flagged = [], []

    a = read("assets.csv")
    year, sum_insured = _number(a["construction_year"]), _number(a["sum_insured_dkk"])
    assets, ex = _exclude(a, "assets.csv", a["asset_id"], [
        (~a["region"].isin(REGIONS), "unknown region"),
        (~a["asset_type"].isin(ASSET_TYPES), "unknown asset_type"),
        (~(year % 1 == 0), "construction_year not an integer"),
        (~(sum_insured > 0), "sum_insured_dkk not a positive number"),
    ])
    excluded.append(ex)
    assets = assets.assign(construction_year=year[assets.index].astype(int), sum_insured_dkk=sum_insured)

    p = read("policies.csv")
    peril = p["peril"].str.strip().str.lower()
    inception, expiry, premium = _date(p["inception_date"]), _date(p["expiry_date"]), _number(p["annual_premium"])
    policies, ex = _exclude(p, "policies.csv", p["policy_id"], [
        (~p["asset_id"].isin(assets["asset_id"]), "orphan asset_id"),
        (~peril.isin(PERILS), "unknown peril"),
        (inception.isna(), "unparseable inception_date"),
        (expiry.isna(), "unparseable expiry_date"),
        (expiry <= inception, "expiry_date not after inception_date"),
        (~(premium > 0), "annual_premium not a positive number"),
        (~p["currency"].isin(CURRENCIES), "unknown currency"),
    ])
    excluded.append(ex)
    fixed = policies["peril"] != peril[policies.index]
    flagged.append(_rows("policies.csv", policies["policy_id"][fixed],
                         "fixed peril: '" + policies["peril"][fixed] + "' -> " + peril[policies.index][fixed]))
    policies = policies.assign(peril=peril, inception_date=inception, expiry_date=expiry, annual_premium=premium)

    pairs = policies.merge(policies, on=["asset_id", "peril"], suffixes=("", "_earlier"))
    earlier = (pairs["inception_date_earlier"] < pairs["inception_date"]) | (
        (pairs["inception_date_earlier"] == pairs["inception_date"]) & (pairs["policy_id_earlier"] < pairs["policy_id"]))
    overlap_days = (pairs["expiry_date_earlier"] - pairs["inception_date"]).dt.days
    pairs = pairs[earlier & (overlap_days > OVERLAP_FLAG_DAYS)]
    flagged.append(_rows("policies.csv", pairs["policy_id"],
                         "term overlaps: " + pairs["policy_id_earlier"] + " (same asset+peril)"))

    c = read("claims.csv")
    # Some claim dates are DD-MM-YYYY; ISO is tried first.
    dates = {col: _date(c[col]).fillna(_date(c[col], "%d-%m-%Y")) for col in ("loss_date", "reported_date")}
    paid, reserve = _number(c["paid_amount"]), _number(c["reserve_amount"])
    claims, ex = _exclude(c, "claims.csv", c["claim_id"], [
        (~c["policy_id"].isin(policies["policy_id"]), "orphan policy_id"),
        (dates["loss_date"].isna(), "unparseable loss_date"),
        (dates["reported_date"].isna(), "unparseable reported_date"),
        (paid.isna(), "paid_amount not a number"),
        (~(reserve >= 0), "reserve_amount not a non-negative number"),
        (~c["currency"].isin(CURRENCIES), "unknown currency"),
        (~c["status"].isin(STATUSES), "unknown status"),
    ])
    excluded.append(ex)
    for col, parsed in dates.items():
        fixed = _date(claims[col]).isna()
        flagged.append(_rows("claims.csv", claims["claim_id"][fixed],
                             f"fixed {col}: '" + claims[col][fixed] + "' -> " + parsed[claims.index][fixed].dt.strftime("%Y-%m-%d")))
    claims = claims.assign(**dates, paid_amount=paid, reserve_amount=reserve)
    policy_inception = claims["policy_id"].map(policies.set_index("policy_id")["inception_date"])
    for bad, reason in [
        (claims["loss_date"] < policy_inception, "loss_date before policy inception"),
        (claims["paid_amount"] < 0, "negative paid_amount"),
        ((claims["status"] == "settled") & (claims["reserve_amount"] > 0), "settled with reserve_amount > 0"),
    ]:
        flagged.append(_rows("claims.csv", claims["claim_id"][bad], reason))

    f = read("fx_rates.csv")
    month, rate = _date(f["month"], "%Y-%m"), _number(f["rate_dkk_per_unit"])
    fx_rates, ex = _exclude(f, "fx_rates.csv", f["month"] + " " + f["currency"], [
        (month.isna(), "unparseable month"),
        (~f["currency"].isin(CURRENCIES), "unknown currency"),
        (rate.isna(), "rate_dkk_per_unit not a number"),
    ])
    excluded.append(ex)
    fx_rates = fx_rates.assign(month=month, rate_dkk_per_unit=rate)

    tables = {"assets": assets, "policies": policies, "claims": claims, "fx_rates": fx_rates}  # FK order
    for df in tables.values():
        for col in df.select_dtypes("datetime").columns:
            df[col] = df[col].dt.date
    return tables, pd.concat(excluded, ignore_index=True), pd.concat(flagged, ignore_index=True)


def load(engine, data_dir):
    """Replace everything in the DB with a fresh load of the CSVs, in one transaction (safe on restart)."""
    tables, excluded, flagged = clean(data_dir)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE assets, policies, claims, fx_rates, excluded_rows, flagged_rows RESTART IDENTITY"))
        for name, df in [*tables.items(), ("excluded_rows", excluded), ("flagged_rows", flagged)]:
            df.to_sql(name, conn, if_exists="append", index=False)
    log.info("Loaded %s; excluded %d rows; flagged %d issues",
             ", ".join(f"{name} {len(df)}" for name, df in tables.items()), len(excluded), len(flagged))
