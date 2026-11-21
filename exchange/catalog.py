from dataclasses import dataclass
import json
import sqlite3

from exchange.codec import BatchPacket, decode_packet, packet_digest
from exchange.paired_codec import PairedPacket, decode_paired_packet, paired_packet_digest
from ledger import InvalidInput, require_id, require_key


@dataclass(frozen=True)
class ReceivedBatch:
    receipt_id: int
    packet: BatchPacket | PairedPacket
    wire: bytes
    digest: str

    @property
    def is_paired(self) -> bool:
        return isinstance(self.packet, PairedPacket)

    @property
    def issue_id(self) -> str:
        return self.packet.issue_id

    @property
    def shift_id(self) -> str:
        return self.packet.shift_id


def _decode(wire: bytes):
    try:
        envelope = json.loads(wire.decode('utf-8'))
        version = envelope['payload']['version']
    except InvalidInput:
        raise
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
        raise InvalidInput('invalid packet structure or encoding') from error
    if type(version) is not int:
        raise InvalidInput('unsupported packet version')
    if version == 1:
        return decode_packet(wire)
    if version == 2:
        return decode_paired_packet(wire)
    raise InvalidInput('unsupported packet version')


def _digest_for(packet) -> str:
    if isinstance(packet, PairedPacket):
        return paired_packet_digest(packet)
    if isinstance(packet, BatchPacket):
        return packet_digest(packet)
    raise InvalidInput('unknown packet type')


def _received(row) -> ReceivedBatch | None:
    if row is None:
        return None
    receipt_id, wire, digest = row
    packet = _decode(wire)
    if _digest_for(packet) != digest:
        raise InvalidInput('stored receipt digest does not match its packet body')
    return ReceivedBatch(receipt_id, packet, wire, digest)


def load_receipt(db: sqlite3.Connection, receipt_id: int) -> ReceivedBatch | None:
    receipt_id = require_id(receipt_id, 'receipt_id')
    row = db.execute(
        'SELECT receipt_id, wire, digest FROM intake WHERE receipt_id = ?', (receipt_id,)
    ).fetchone()
    return _received(row)


def load_by_issue(db: sqlite3.Connection, issue_id: str) -> ReceivedBatch | None:
    issue_id = require_key(issue_id, 'issue_id')
    row = db.execute(
        'SELECT receipt_id, wire, digest FROM intake WHERE issue_id = ?', (issue_id,)
    ).fetchone()
    return _received(row)


def store_receipt(db: sqlite3.Connection, packet, wire: bytes) -> int:
    cursor = db.execute(
        'INSERT INTO intake(issue_id, wire, digest) VALUES (?, ?, ?)',
        (packet.issue_id, wire, _digest_for(packet)),
    )
    return cursor.lastrowid
