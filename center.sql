BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS intake (
    receipt_id INTEGER PRIMARY KEY,
    issue_id TEXT NOT NULL UNIQUE,
    wire BLOB NOT NULL,
    digest TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'v1' CHECK (kind IN ('v1', 'pair')),
    m_hex TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('reachable', 'unreachable')),
    mass_numerator TEXT NOT NULL,
    mass_denominator TEXT NOT NULL,
    probability_numerator TEXT,
    probability_denominator TEXT
);

CREATE TABLE IF NOT EXISTS pair_report_cells (
    report_id INTEGER NOT NULL REFERENCES reports(report_id),
    position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 3),
    numerator TEXT NOT NULL,
    denominator TEXT NOT NULL,
    PRIMARY KEY (report_id, position)
);

CREATE TABLE IF NOT EXISTS report_parent_designs (
    report_id INTEGER NOT NULL REFERENCES reports(report_id),
    parent_position INTEGER NOT NULL,
    design_position INTEGER NOT NULL,
    design_id INTEGER NOT NULL,
    revision_id INTEGER NOT NULL,
    protocol_version TEXT NOT NULL,
    PRIMARY KEY (report_id, parent_position, design_position)
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
