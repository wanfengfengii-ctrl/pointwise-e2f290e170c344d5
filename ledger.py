from contextlib import contextmanager
from pathlib import Path
import sqlite3


class InvalidInput(ValueError):
    """The proposed input does not meet the ledger contract."""


class UnknownRecord(LookupError):
    """A pinned source or input record does not exist."""


def require_key(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(f'{field} must be nonempty text')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise InvalidInput(f'{field} must be valid UTF-8 text') from error
    return value


def require_id(value: object, field: str) -> int:
    if type(value) is not int or not 0 < value < 2**63:
        raise InvalidInput(f'{field} must be a positive SQLite row number')
    return value


@contextmanager
def transaction(db: sqlite3.Connection, *, allow_nested: bool = False):
    if db.in_transaction:
        if not allow_nested:
            raise InvalidInput('this operation requires its own transaction')
        db.execute('SAVEPOINT ledger_operation')
        try:
            yield
            db.execute('RELEASE ledger_operation')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK TO ledger_operation')
                db.execute('RELEASE ledger_operation')
            raise
        return

    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _migrate_station(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute('PRAGMA table_info(issued_batches)')}
    if columns and 'design_id' in columns:
        not_null = any(
            row[1] == 'design_id' and bool(row[3])
            for row in db.execute('PRAGMA table_info(issued_batches)')
        )
        if not_null:
            db.execute('PRAGMA foreign_keys = OFF')
            db.execute('BEGIN IMMEDIATE')
            try:
                # sample_issues references issued_batches, so rebuild both.
                db.execute(
                    'CREATE TABLE issued_batches_v2 ( '
                    'issue_id TEXT NOT NULL PRIMARY KEY, '
                    'design_id INTEGER REFERENCES designs(design_id), '
                    'wire BLOB NOT NULL)'
                )
                db.execute(
                    'INSERT INTO issued_batches_v2(issue_id, design_id, wire) '
                    'SELECT issue_id, design_id, wire FROM issued_batches'
                )
                db.execute(
                    'CREATE TABLE sample_issues_v2 ( '
                    'sample_key TEXT NOT NULL, '
                    'position INTEGER NOT NULL CHECK (position IN (0, 1)), '
                    'issue_id TEXT NOT NULL REFERENCES issued_batches_v2(issue_id), '
                    'PRIMARY KEY (sample_key, position))'
                )
                db.execute(
                    'INSERT INTO sample_issues_v2(sample_key, position, issue_id) '
                    'SELECT sample_key, position, issue_id FROM sample_issues'
                )
                db.execute('DROP TABLE sample_issues')
                db.execute('DROP TABLE issued_batches')
                db.execute('ALTER TABLE issued_batches_v2 RENAME TO issued_batches')
                db.execute('ALTER TABLE sample_issues_v2 RENAME TO sample_issues')
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.execute('PRAGMA foreign_keys = ON')
            violations = db.execute('PRAGMA foreign_key_check').fetchall()
            if violations:
                raise InvalidInput('station migration left unresolved foreign keys')


def _migrate_center(db: sqlite3.Connection) -> None:
    report_columns = {row[1] for row in db.execute('PRAGMA table_info(reports)')}
    if report_columns and 'kind' not in report_columns:
        db.execute('PRAGMA foreign_keys = OFF')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute(
                'CREATE TABLE reports_v2 ( '
                'report_id INTEGER PRIMARY KEY, '
                "kind TEXT NOT NULL DEFAULT 'v1' CHECK (kind IN ('v1', 'pair')), "
                'm_hex TEXT NOT NULL, '
                "status TEXT NOT NULL CHECK (status IN ('reachable', 'unreachable')), "
                'mass_numerator TEXT NOT NULL, '
                'mass_denominator TEXT NOT NULL, '
                'probability_numerator TEXT, '
                'probability_denominator TEXT)'
            )
            db.execute(
                "INSERT INTO reports_v2(report_id, kind, m_hex, status, mass_numerator, "
                'mass_denominator, probability_numerator, probability_denominator) '
                "SELECT report_id, 'v1', m_hex, status, mass_numerator, mass_denominator, "
                'probability_numerator, probability_denominator FROM reports'
            )
            db.execute(
                'CREATE TABLE report_parents_v2 ( '
                'report_id INTEGER NOT NULL REFERENCES reports_v2(report_id), '
                'position INTEGER NOT NULL CHECK (position IN (0, 1)), '
                'receipt_id INTEGER NOT NULL REFERENCES intake(receipt_id), '
                'digest TEXT NOT NULL, '
                'PRIMARY KEY (report_id, position), '
                'UNIQUE (report_id, receipt_id))'
            )
            db.execute(
                'INSERT INTO report_parents_v2(report_id, position, receipt_id, digest) '
                'SELECT report_id, position, receipt_id, digest FROM report_parents'
            )
            db.execute(
                'CREATE TABLE report_receipts_v2 ( '
                'report_id INTEGER PRIMARY KEY REFERENCES reports_v2(report_id), '
                'token TEXT NOT NULL UNIQUE)'
            )
            db.execute(
                'INSERT INTO report_receipts_v2(report_id, token) '
                'SELECT report_id, token FROM report_receipts'
            )
            db.execute('DROP TABLE report_receipts')
            db.execute('DROP TABLE report_parents')
            db.execute('DROP TABLE reports')
            db.execute('ALTER TABLE reports_v2 RENAME TO reports')
            db.execute('ALTER TABLE report_parents_v2 RENAME TO report_parents')
            db.execute('ALTER TABLE report_receipts_v2 RENAME TO report_receipts')
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.execute('PRAGMA foreign_keys = ON')
        violations = db.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise InvalidInput('center migration left unresolved foreign keys')


def _initialize(db: sqlite3.Connection, script_name: str) -> None:
    if db.in_transaction:
        raise InvalidInput('initialize outside a transaction')
    db.execute('PRAGMA foreign_keys = ON')
    script = Path(__file__).with_name(script_name).read_text(encoding='utf-8')
    migration = _migrate_station if script_name == 'station.sql' else _migrate_center
    db.execute('BEGIN IMMEDIATE')
    try:
        db.executescript(script)
    except BaseException:
        db.rollback()
        raise
    # Foreign-key toggles only take effect outside a transaction.
    db.commit()
    migration(db)


def init_station(db: sqlite3.Connection) -> None:
    _initialize(db, 'station.sql')


def init_center(db: sqlite3.Connection) -> None:
    _initialize(db, 'center.sql')


def _open(path, initialize) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        initialize(db)
    except BaseException:
        db.close()
        raise
    return db


def open_station(path) -> sqlite3.Connection:
    return _open(path, init_station)


def open_center(path) -> sqlite3.Connection:
    return _open(path, init_center)
