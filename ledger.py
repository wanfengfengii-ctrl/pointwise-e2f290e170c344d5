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


def _initialize(db: sqlite3.Connection, script_name: str) -> None:
    if db.in_transaction:
        raise InvalidInput('initialize outside a transaction')
    db.execute('PRAGMA foreign_keys = ON')
    script = Path(__file__).with_name(script_name).read_text(encoding='utf-8')
    try:
        db.executescript(script)
    except BaseException:
        db.rollback()
        raise


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
