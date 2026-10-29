-- Cleaned data, loaded by core on startup. Rows that fail cleaning go to excluded_rows.

CREATE TABLE assets (
    asset_id          TEXT PRIMARY KEY,
    portfolio_id      TEXT NOT NULL,
    region            TEXT NOT NULL CHECK (region IN ('Hovedstaden', 'Midtjylland', 'Nordjylland', 'Sjaelland', 'Syddanmark')),
    asset_type        TEXT NOT NULL CHECK (asset_type IN ('agricultural', 'commercial', 'industrial', 'public', 'residential')),
    construction_year SMALLINT NOT NULL,
    sum_insured_dkk   NUMERIC(14, 2) NOT NULL CHECK (sum_insured_dkk > 0)
);

CREATE TABLE policies (
    policy_id      TEXT PRIMARY KEY,
    asset_id       TEXT NOT NULL REFERENCES assets (asset_id),
    peril          TEXT NOT NULL CHECK (peril IN ('fire', 'flood', 'hail', 'storm', 'subsidence')),
    inception_date DATE NOT NULL,
    expiry_date    DATE NOT NULL,
    annual_premium NUMERIC(14, 2) NOT NULL CHECK (annual_premium > 0),
    currency       TEXT NOT NULL CHECK (currency IN ('DKK', 'EUR')),
    CHECK (expiry_date > inception_date)
);

CREATE TABLE claims (
    claim_id       TEXT PRIMARY KEY,
    policy_id      TEXT NOT NULL REFERENCES policies (policy_id),
    loss_date      DATE NOT NULL,
    reported_date  DATE NOT NULL,
    paid_amount    NUMERIC(14, 2) NOT NULL,  -- negatives present in source; policy not decided yet
    reserve_amount NUMERIC(14, 2) NOT NULL CHECK (reserve_amount >= 0),
    currency       TEXT NOT NULL CHECK (currency IN ('DKK', 'EUR')),
    status         TEXT NOT NULL CHECK (status IN ('open', 'settled', 'withdrawn', 'declined'))
);

CREATE TABLE fx_rates (
    month             DATE NOT NULL,  -- 'YYYY-MM' stored as first of month
    currency          TEXT NOT NULL CHECK (currency IN ('DKK', 'EUR')),
    rate_dkk_per_unit NUMERIC(10, 4) NOT NULL,
    PRIMARY KEY (month, currency)
);

CREATE TABLE excluded_rows (
    id          SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,  -- e.g. 'claims.csv'
    row_id      TEXT NOT NULL,  -- the row's own id, e.g. claim_id
    reason      TEXT NOT NULL
);
