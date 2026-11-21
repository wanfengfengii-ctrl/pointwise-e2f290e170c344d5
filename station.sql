BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS shifts (
    shift_id TEXT NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS shared_specimens (
    shared_key TEXT NOT NULL PRIMARY KEY,
    registration TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS specimens (
    specimen_id INTEGER PRIMARY KEY,
    shift_id TEXT NOT NULL REFERENCES shifts(shift_id),
    local_id TEXT NOT NULL,
    shared_key TEXT REFERENCES shared_specimens(shared_key),
    UNIQUE (shift_id, local_id)
);

CREATE TABLE IF NOT EXISTS reading_revisions (
    revision_id INTEGER PRIMARY KEY,
    shift_id TEXT NOT NULL REFERENCES shifts(shift_id),
    previous_revision_id INTEGER REFERENCES reading_revisions(revision_id),
    UNIQUE (shift_id, revision_id)
);

CREATE TABLE IF NOT EXISTS observations (
    revision_id INTEGER NOT NULL REFERENCES reading_revisions(revision_id),
    specimen_id INTEGER NOT NULL REFERENCES specimens(specimen_id),
    microns_hex TEXT NOT NULL,
    PRIMARY KEY (revision_id, specimen_id)
);

CREATE TABLE IF NOT EXISTS protocols (
    shift_id TEXT NOT NULL REFERENCES shifts(shift_id),
    version TEXT NOT NULL,
    threshold_hex TEXT NOT NULL,
    PRIMARY KEY (shift_id, version)
);

CREATE TABLE IF NOT EXISTS designs (
    design_id INTEGER PRIMARY KEY,
    shift_id TEXT NOT NULL,
    revision_id INTEGER NOT NULL,
    protocol_version TEXT NOT NULL,
    FOREIGN KEY (shift_id, revision_id) REFERENCES reading_revisions(shift_id, revision_id),
    FOREIGN KEY (shift_id, protocol_version) REFERENCES protocols(shift_id, version)
);

CREATE TABLE IF NOT EXISTS design_layers (
    design_id INTEGER NOT NULL REFERENCES designs(design_id),
    layer_name TEXT NOT NULL,
    quota INTEGER NOT NULL CHECK (quota >= 0),
    PRIMARY KEY (design_id, layer_name)
);

CREATE TABLE IF NOT EXISTS frame_members (
    design_id INTEGER NOT NULL,
    layer_name TEXT NOT NULL,
    specimen_id INTEGER NOT NULL REFERENCES specimens(specimen_id),
    abnormal INTEGER NOT NULL CHECK (abnormal IN (0, 1)),
    PRIMARY KEY (design_id, specimen_id),
    FOREIGN KEY (design_id, layer_name) REFERENCES design_layers(design_id, layer_name)
);

CREATE TABLE IF NOT EXISTS issued_batches (
    issue_id TEXT NOT NULL PRIMARY KEY,
    design_id INTEGER NOT NULL REFERENCES designs(design_id),
    wire BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS sample_issues (
    sample_key TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position IN (0, 1)),
    issue_id TEXT NOT NULL REFERENCES issued_batches(issue_id),
    PRIMARY KEY (sample_key, position)
);

COMMIT;
