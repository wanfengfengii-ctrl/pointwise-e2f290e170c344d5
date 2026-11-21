"""Frozen-design provenance captured for paired-review reports."""
from dataclasses import dataclass
import sqlite3

from exchange.catalog import ReceivedBatch
from exchange.codec import BatchPacket
from exchange.paired_codec import PairedPacket


@dataclass(frozen=True)
class PairDesignRef:
    design_id: int
    revision_id: int
    protocol_version: str


@dataclass(frozen=True)
class PairParentReference:
    receipt_id: int
    issue_id: str
    shift_id: str
    digest: str
    designs: tuple[PairDesignRef, ...]


def _reference(batch: ReceivedBatch) -> PairParentReference:
    packet = batch.packet
    if isinstance(packet, PairedPacket):
        designs = (
            PairDesignRef(packet.old_design_id, packet.old_revision_id, packet.old_protocol_version),
            PairDesignRef(packet.new_design_id, packet.new_revision_id, packet.new_protocol_version),
        )
    elif isinstance(packet, BatchPacket):
        designs = (
            PairDesignRef(packet.design_id, packet.revision_id, packet.protocol_version),
        )
    else:
        raise TypeError('unsupported parent packet type')
    return PairParentReference(batch.receipt_id, packet.issue_id, packet.shift_id, batch.digest, designs)


def capture_pair_parents(
    paired: ReceivedBatch, other: ReceivedBatch
) -> tuple[PairParentReference, PairParentReference]:
    return _reference(paired), _reference(other)


def store_pair_parents(
    db: sqlite3.Connection,
    report_id: int,
    parents: tuple[PairParentReference, PairParentReference],
) -> None:
    db.executemany(
        'INSERT INTO report_parents(report_id, position, receipt_id, digest) VALUES (?, ?, ?, ?)',
        (
            (report_id, position, parent.receipt_id, parent.digest)
            for position, parent in enumerate(parents)
        ),
    )
    for parent_position, parent in enumerate(parents):
        db.executemany(
            'INSERT INTO report_parent_designs(report_id, parent_position, design_position, '
            'design_id, revision_id, protocol_version) VALUES (?, ?, ?, ?, ?, ?)',
            (
                (report_id, parent_position, design_position, design.design_id,
                 design.revision_id, design.protocol_version)
                for design_position, design in enumerate(parent.designs)
            ),
        )


def read_pair_parents(
    db: sqlite3.Connection, report_id: int
) -> tuple[PairParentReference, PairParentReference]:
    rows = db.execute(
        'SELECT position, receipt_id, digest FROM report_parents WHERE report_id = ? ORDER BY position',
        (report_id,),
    ).fetchall()
    if [row[0] for row in rows] != [0, 1]:
        raise sqlite3.IntegrityError(f'report {report_id} does not have two ordered parents')
    parents = []
    design_rows = db.execute(
        'SELECT parent_position, design_position, design_id, revision_id, protocol_version '
        'FROM report_parent_designs WHERE report_id = ? '
        'ORDER BY parent_position, design_position',
        (report_id,),
    ).fetchall()
    designs_by_parent: dict[int, list[PairDesignRef]] = {0: [], 1: []}
    for parent_position, design_position, design_id, revision_id, protocol_version in design_rows:
        designs_by_parent[parent_position].append(
            PairDesignRef(design_id, revision_id, protocol_version)
        )
    for position, receipt_id, digest in rows:
        batch = load_receipt_checked(db, receipt_id, digest)
        stored = tuple(designs_by_parent[position])
        reference = _reference(batch)
        if stored != reference.designs:
            raise sqlite3.IntegrityError(
                f'report {report_id} has inconsistent frozen designs for parent {receipt_id}'
            )
        parents.append(reference)
    return tuple(parents)


def load_receipt_checked(db: sqlite3.Connection, receipt_id: int, digest: str) -> ReceivedBatch:
    from exchange.catalog import load_receipt

    batch = load_receipt(db, receipt_id)
    if batch is None or batch.digest != digest:
        raise sqlite3.IntegrityError(f'report has an inconsistent parent {receipt_id}')
    return batch
