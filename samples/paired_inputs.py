"""Build fixed paired-review inputs with the existing V1 preparation APIs."""
from contextlib import closing
from fractions import Fraction

from analysis.risk import publish
from exchange.catalog import load_receipt
from exchange.intake import receive
from exchange.issue import issue
from ledger import open_center, open_station
from register.revisions import revise
from report.retrieve import read
from sampling.design import freeze
from sampling.protocols import register_protocol


def _freeze(db, shift, changes, members):
    revision = revise(db, shift, changes)
    return freeze(db, shift, revision, "inspection", {"rack": members}, {"rack": 1})


def private_inputs(left, right):
    """Return frozen design numbers. Use fresh station databases for each case."""
    register_protocol(left, "甲班", "inspection", 10)
    register_protocol(right, "乙班", "inspection", 10)
    members = ("plate-a", "plate-b")
    return {
        "old": _freeze(left, "甲班", {"plate-a": (None, 12), "plate-b": (None, 0)}, members),
        "kept": _freeze(left, "甲班", {"plate-a": (None, 11), "plate-b": (None, 1)}, members),
        "swapped": _freeze(left, "甲班", {"plate-a": (None, 0), "plate-b": (None, 12)}, members),
        "replaced": _freeze(left, "甲班", {"plate-d": (None, 0)}, ("plate-d", "plate-b")),
        "other": _freeze(right, "乙班", {"plate-a": (None, 0)}, ("plate-a",)),
    }


def shared_inputs(left, right):
    """Use a different local label for the same shared specimen in the new frame."""
    register_protocol(left, "甲班", "inspection", 10)
    register_protocol(right, "乙班", "inspection", 10)
    return {
        "old": _freeze(left, "甲班", {"x-before": ("x", 0), "a": (None, 12), "c": (None, 0)},
                       ("x-before", "a", "c")),
        "new": _freeze(left, "甲班", {"x-after": ("x", 12), "a": (None, 0), "c": (None, 1)},
                       ("x-after", "a", "c")),
        "other": _freeze(right, "乙班", {"x-right": ("x", 0), "b": (None, 0)}, ("x-right", "b")),
    }


def _legacy_receipts(center, prepare):
    with closing(open_station(":memory:")) as left, closing(open_station(":memory:")) as right:
        designs = prepare(left, right)
        return {
            name: receive(center, *issue(right if name == "other" else left, design_id))
            for name, design_id in designs.items()
        }


def _legacy_result(center, receipts, name, m):
    signed = publish(center, receipts[name], receipts["other"], m)
    if read(center, signed.record.report_id) != signed:
        raise RuntimeError("V1 archived report differs from its issued value")
    return signed.record.condition_mass, signed.record.zero_probability


def main():
    with closing(open_center(":memory:")) as center:
        receipts = _legacy_receipts(center, private_inputs)
        first = load_receipt(center, receipts["old"]).packet.evidence
        for name in ("old", "kept", "swapped", "replaced"):
            evidence = load_receipt(center, receipts[name]).packet.evidence
            mass, miss = _legacy_result(center, receipts, name, 2)
            if evidence != first or (mass, miss) != (Fraction(1), Fraction(1, 2)):
                raise RuntimeError(f"unexpected V1 private result for {name}: {mass}, {miss}")
            print(f"V1 private {name} m=2 mass={mass} miss={miss}")

    with closing(open_center(":memory:")) as center:
        receipts = _legacy_receipts(center, shared_inputs)
        for m, mass, expected_old, expected_new in (
            (1, Fraction(1, 6), Fraction(1), Fraction(0)),
            (2, Fraction(5, 6), Fraction(3, 5), Fraction(4, 5)),
            (3, Fraction(0), None, None),
        ):
            old = _legacy_result(center, receipts, "old", m)
            new = _legacy_result(center, receipts, "new", m)
            if old != (mass, expected_old) or new != (mass, expected_new):
                raise RuntimeError(f"unexpected V1 shared result for m={m}: {old}, {new}")
            print(f"V1 shared m={m} mass={mass} old_miss={old[1]} new_miss={new[1]}")


if __name__ == "__main__":
    main()
