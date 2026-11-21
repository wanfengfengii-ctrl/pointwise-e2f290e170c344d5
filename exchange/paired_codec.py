"""Canonical JSON encoding for version-2 paired batches."""
from dataclasses import dataclass
import hashlib
import json

from exchange.paired_evidence import PairedEvidence, PairedLayerEvidence, PairedSharedMark, validate_paired_evidence
from exchange.codec import _canonical
from ledger import InvalidInput, require_id, require_key


@dataclass(frozen=True)
class PairedPacket:
    issue_id: str
    shift_id: str
    old_design_id: int
    old_revision_id: int
    old_protocol_version: str
    new_design_id: int
    new_revision_id: int
    new_protocol_version: str
    evidence: PairedEvidence


def _paired_payload(packet: PairedPacket) -> dict:
    validate_paired_evidence(packet.evidence)
    return {
        'version': 2,
        'issue_id': require_key(packet.issue_id, 'issue_id'),
        'shift_id': require_key(packet.shift_id, 'shift_id'),
        'designs': [
            {
                'design_id': require_id(packet.old_design_id, 'old design_id'),
                'revision_id': require_id(packet.old_revision_id, 'old revision_id'),
                'protocol_version': require_key(packet.old_protocol_version, 'old protocol version'),
            },
            {
                'design_id': require_id(packet.new_design_id, 'new design_id'),
                'revision_id': require_id(packet.new_revision_id, 'new revision_id'),
                'protocol_version': require_key(packet.new_protocol_version, 'new protocol version'),
            },
        ],
        'layers': [
            {
                'name': layer.name,
                'quota': layer.quota,
                'size': layer.size_declared,
                'shared': [
                    [mark.key, mark.old_abnormal, mark.new_abnormal]
                    for mark in sorted(layer.shared, key=lambda item: item.key)
                ],
                'private_00': layer.private_00,
                'private_01': layer.private_01,
                'private_10': layer.private_10,
                'private_11': layer.private_11,
            }
            for layer in sorted(packet.evidence.layers, key=lambda item: item.name)
        ],
    }


def paired_packet_digest(packet: PairedPacket) -> str:
    return hashlib.sha256(_canonical(_paired_payload(packet))).hexdigest()


def encode_paired_packet(packet: PairedPacket) -> bytes:
    payload = _paired_payload(packet)
    return _canonical({'payload': payload, 'sha256': hashlib.sha256(_canonical(payload)).hexdigest()})


def _decode_paired_evidence(payload: dict) -> PairedEvidence:
    layers = payload['layers']
    if type(layers) is not list:
        raise InvalidInput('paired packet layers must be an array')
    evidence = []
    for layer in layers:
        shared = layer['shared']
        if type(shared) is not list:
            raise InvalidInput('paired shared marks must be an array')
        marks = []
        for mark in shared:
            if type(mark) is not list or len(mark) != 3:
                raise InvalidInput('each paired shared mark needs a key and two flags')
            marks.append(PairedSharedMark(*mark))
        evidence.append(
            PairedLayerEvidence(
                layer['name'],
                layer['quota'],
                layer['size'],
                tuple(marks),
                layer['private_00'],
                layer['private_01'],
                layer['private_10'],
                layer['private_11'],
            )
        )
    return PairedEvidence(tuple(evidence))


def decode_paired_packet(wire: bytes) -> PairedPacket:
    if not isinstance(wire, bytes):
        raise InvalidInput('paired packet must be bytes')
    try:
        envelope = json.loads(wire.decode('utf-8'))
        payload = envelope['payload']
        version = payload['version']
        if type(version) is not int or version != 2:
            raise InvalidInput('unsupported paired packet version')
        designs = payload['designs']
        if type(designs) is not list or len(designs) != 2:
            raise InvalidInput('a paired packet must list exactly two frozen designs')
        packet = PairedPacket(
            payload['issue_id'],
            payload['shift_id'],
            designs[0]['design_id'],
            designs[0]['revision_id'],
            designs[0]['protocol_version'],
            designs[1]['design_id'],
            designs[1]['revision_id'],
            designs[1]['protocol_version'],
            _decode_paired_evidence(payload),
        )
        validate_paired_evidence(packet.evidence)
        if encode_paired_packet(packet) != wire:
            raise InvalidInput('paired packet checksum or canonical encoding is invalid')
    except InvalidInput:
        raise
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise InvalidInput('invalid paired packet structure or encoding') from error
    validate_paired_evidence(packet.evidence)
    return packet
