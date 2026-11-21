BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS intake (
    receipt_id INTEGER PRIMARY KEY,
    issue_id TEXT NOT NULL UNIQUE,
    wire BLOB NOT NULL,
    digest TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id INTEGER PRIMARY KEY,
    m_hex TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('reachable', 'unreachable')),
    mass_numerator TEXT NOT NULL,
    mass_denominator TEXT NOT NULL,
    probability_numerator TEXT,
    probability_denominator TEXT,
    CHECK (
        (status = 'reachable' AND probability_numerator IS NOT NULL AND probability_denominator IS NOT NULL)
        OR
        (status = 'unreachable' AND probability_numerator IS NULL AND probability_denominator IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS report_parents (
    report_id INTEGER NOT NULL REFERENCES reports(report_id),
    position INTEGER NOT NULL CHECK (position IN (0, 1)),
    receipt_id INTEGER NOT NULL REFERENCES intake(receipt_id),
    digest TEXT NOT NULL,
    PRIMARY KEY (report_id, position),
    UNIQUE (report_id, receipt_id)
);

CREATE TABLE IF NOT EXISTS report_receipts (
    report_id INTEGER PRIMARY KEY REFERENCES reports(report_id),
    token TEXT NOT NULL UNIQUE
);

COMMIT;
