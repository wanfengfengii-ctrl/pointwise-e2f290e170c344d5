from dataclasses import dataclass
import hashlib
import json

from exchange.evidence import LayerEvidence, SamplingEvidence, SharedMark, validate_evidence
from ledger import InvalidInput, require_id, require_key


@dataclass(frozen=True)
class BatchPacket:
    issue_id: str
    shift_id: str
    design_id: int
    revision_id: int
    protocol_version: str
    evidence: SamplingEvidence


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def _payload(packet: BatchPacket) -> dict:
    validate_evidence(packet.evidence)
    return {
        'version': 1,
        'issue_id': require_key(packet.issue_id, 'issue_id'),
        'shift_id': require_key(packet.shift_id, 'shift_id'),
        'design_id': require_id(packet.design_id, 'design_id'),
        'revision_id': require_id(packet.revision_id, 'revision_id'),
        'protocol_version': require_key(packet.protocol_version, 'protocol version'),
        'layers': [
            {
                'name': layer.name,
                'quota': layer.quota,
                'shared': [
                    [mark.key, mark.abnormal]
                    for mark in sorted(layer.shared, key=lambda item: item.key)
                ],
                'private_normal': layer.private_normal,
                'private_abnormal': layer.private_abnormal,
            }
            for layer in sorted(packet.evidence.layers, key=lambda item: item.name)
        ],
    }


def _digest(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def packet_digest(packet: BatchPacket) -> str:
    return _digest(_payload(packet))


def encode_packet(packet: BatchPacket) -> bytes:
    payload = _payload(packet)
    return _canonical({'payload': payload, 'sha256': _digest(payload)})


def _decode_evidence(payload: dict) -> SamplingEvidence:
    layers = payload['layers']
    if type(layers) is not list:
        raise InvalidInput('packet layers must be an array')
    evidence = []
    for layer in layers:
        shared = layer['shared']
        if type(shared) is not list:
            raise InvalidInput('shared marks must be an array')
        marks = []
        for mark in shared:
            if type(mark) is not list or len(mark) != 2:
                raise InvalidInput('each shared mark needs a key and a flag')
            marks.append(SharedMark(*mark))
        evidence.append(
            LayerEvidence(
                layer['name'], layer['quota'], tuple(marks),
                layer['private_normal'], layer['private_abnormal'],
            )
        )
    return SamplingEvidence(tuple(evidence))


def decode_packet(wire: bytes) -> BatchPacket:
    if not isinstance(wire, bytes):
        raise InvalidInput('packet must be bytes')
    try:
        envelope = json.loads(wire.decode('utf-8'))
        payload = envelope['payload']
        version = payload['version']
        if type(version) is not int or version != 1:
            raise InvalidInput('unsupported packet version')
        packet = BatchPacket(
            payload['issue_id'], payload['shift_id'], payload['design_id'],
            payload['revision_id'], payload['protocol_version'], _decode_evidence(payload),
        )
        if encode_packet(packet) != wire:
            raise InvalidInput('packet checksum or canonical encoding is invalid')
    except InvalidInput:
        raise
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise InvalidInput('invalid packet structure or encoding') from error
    return packet
