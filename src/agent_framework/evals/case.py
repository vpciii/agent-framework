"""Eval cases: one file each, a directory of them the eval set.

An **accepted case** holds a whole frozen evidence bundle. A
**seeded-defect case** holds none: it names its accepted case and carries
an edit, and its bundle is computed here, at load. Loading is pure and
strict — a malformed file, or an edit that does not apply exactly once, is
an `EvalCaseError` naming the file (specs/validator-eval-set, plan.md).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast, get_args

from ..errors import EvalCaseError
from ..validator.bundle import CIEvidence, Contract, EvidenceBundle, TaskRef
from ..validator.judgment import CHECK_NAMES

Kind = Literal["accepted", "seeded-defect"]
Expected = Literal["pass", "reject"]


@dataclass(frozen=True)
class Provenance:
    """Where an accepted case was frozen from, and when."""

    repo: str
    pr: int
    head: str  # the pull request's head commit
    frozen: str  # ISO date


@dataclass(frozen=True)
class Replacement:
    """One exact replacement of a seeded edit: `find` must occur exactly
    once in `where` — "diff", or the path of a test file in the bundle."""

    where: str
    find: str
    put: str


@dataclass(frozen=True)
class EvalCase:
    """One frozen bundle with the outcome a human expects of the judgment."""

    id: str  # the file's name, without `.json`
    kind: Kind
    expected: Expected
    reason: str
    provenance: Provenance  # a seeded-defect case's is its accepted case's
    bundle: EvidenceBundle
    check: str | None = None  # the checklist item, when `reject` is expected
    base: str | None = None  # seeded-defect: the accepted case's id
    edit: tuple[Replacement, ...] = ()


# ---- strict reading -------------------------------------------------------


def _field[T](data: dict[str, Any], key: str, kind: type[T], where: str) -> T:
    if key not in data:
        raise EvalCaseError(f"{where}: missing field {key!r}")
    value = data[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise EvalCaseError(
            f"{where}: field {key!r} must be {kind.__name__}, got {type(value).__name__}"
        )
    return value


def _one_of(data: dict[str, Any], key: str, allowed: tuple[str, ...], where: str) -> str:
    value = _field(data, key, str, where)
    if value not in allowed:
        raise EvalCaseError(
            f"{where}: field {key!r} must be one of {', '.join(allowed)}; got {value!r}"
        )
    return value


def _strings(value: Any, key: str, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise EvalCaseError(f"{where}: field {key!r} must be a list of strings")
    return tuple(value)


def _string_map(data: dict[str, Any], key: str, where: str) -> dict[str, str]:
    value = _field(data, key, dict, where)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise EvalCaseError(f"{where}: field {key!r} must map strings to strings")
    return dict(value)


def _optional_string(data: dict[str, Any], key: str, where: str) -> str | None:
    return None if data.get(key) is None else _field(data, key, str, where)


def _bundle(data: dict[str, Any], where: str) -> EvidenceBundle:
    task = _field(data, "task", dict, where)
    ci = _field(data, "ci", dict, where)
    contract: Contract | None = None
    if data.get("contract") is not None:
        raw = _field(data, "contract", dict, where)
        cited = _field(raw, "cited_tests", dict, where)
        contract = Contract(
            spec_slug=_optional_string(raw, "spec_slug", where),
            criterion_texts=_string_map(raw, "criterion_texts", where),
            task_block=_optional_string(raw, "task_block", where),
            cited_tests={
                str(sc): _strings(tests, "cited_tests", where) for sc, tests in cited.items()
            },
            read_from=cast(
                "Literal['base', 'head']", _one_of(raw, "read_from", ("base", "head"), where)
            ),
            ref=_field(raw, "ref", str, where),
            problem=_field(raw, "problem", str, where),
        )
    return EvidenceBundle(
        task=TaskRef(
            task_id=_field(task, "task_id", str, where),
            criteria=_strings(task.get("criteria"), "criteria", where),
            is_fix=_field(task, "is_fix", bool, where),
        ),
        diff=_field(data, "diff", str, where),
        tests=_string_map(data, "tests", where),
        ci=CIEvidence(
            green=_field(ci, "green", bool, where),
            summary=_field(ci, "summary", str, where),
        ),
        red_evidence=_optional_string(data, "red_evidence", where),
        contract=contract,
    )


def _edit(raw: Any, where: str) -> tuple[Replacement, ...]:
    if not isinstance(raw, list) or not raw:
        raise EvalCaseError(f"{where}: field 'edit' must be a non-empty list of replacements")
    replacements: list[Replacement] = []
    for item in raw:
        if not isinstance(item, dict):
            raise EvalCaseError(f"{where}: each replacement in 'edit' must be an object")
        replacements.append(
            Replacement(
                where=_field(item, "in", str, where),
                find=_field(item, "replace", str, where),
                put=_field(item, "with", str, where),
            )
        )
    return tuple(replacements)


def _apply(
    bundle: EvidenceBundle, edit: tuple[Replacement, ...], where: str
) -> EvidenceBundle:
    """The bundle with each replacement made — each exactly once in its target."""
    diff, tests = bundle.diff, dict(bundle.tests)
    for r in edit:
        if r.where != "diff" and r.where not in tests:
            raise EvalCaseError(
                f"{where}: the edit names {r.where!r}, which is neither 'diff' nor a "
                "test file in the accepted case's bundle"
            )
        if not r.find:
            raise EvalCaseError(f"{where}: a replacement's 'replace' text is empty")
        if r.find == r.put:
            raise EvalCaseError(f"{where}: a replacement in {r.where!r} changes nothing")
        text = diff if r.where == "diff" else tests[r.where]
        found = text.count(r.find)
        if found != 1:
            raise EvalCaseError(
                f"{where}: the edit's text must be in {r.where!r} exactly once; "
                f"found {found} times: {r.find[:80]!r}"
            )
        changed = text.replace(r.find, r.put)
        if r.where == "diff":
            diff = changed
        else:
            tests[r.where] = changed
    return replace(bundle, diff=diff, tests=tests)


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise EvalCaseError(f"{path}: cannot be read as JSON ({e})") from None
    if not isinstance(data, dict):
        raise EvalCaseError(f"{path}: an eval case is a JSON object, got {type(data).__name__}")
    return data


def _expectation(data: dict[str, Any], where: str) -> tuple[Expected, str | None]:
    expected = cast("Expected", _one_of(data, "expected", get_args(Expected), where))
    check = _optional_string(data, "check", where)
    if expected == "reject":
        if check is None:
            raise EvalCaseError(f"{where}: a 'reject' case needs 'check', its checklist item")
        _one_of(data, "check", CHECK_NAMES, where)
    elif check is not None:
        raise EvalCaseError(f"{where}: a 'pass' case has no 'check'")
    return expected, check


# ---- the public surface ---------------------------------------------------


def load_case(path: Path) -> EvalCase:
    """Read one case file. A seeded-defect case's accepted case is read from
    the same directory, and its edit applied."""
    where = str(path)
    data = _read(path)
    case_id = _field(data, "id", str, where)
    if case_id != path.stem:
        raise EvalCaseError(f"{where}: field 'id' is {case_id!r}; it must be the file's name")
    kind = cast("Kind", _one_of(data, "kind", get_args(Kind), where))
    expected, check = _expectation(data, where)
    reason = _field(data, "reason", str, where)
    if not reason.strip():
        raise EvalCaseError(f"{where}: field 'reason' is blank")

    if kind == "accepted":
        provenance = _field(data, "provenance", dict, where)
        return EvalCase(
            id=case_id, kind=kind, expected=expected, check=check, reason=reason,
            provenance=Provenance(
                repo=_field(provenance, "repo", str, where),
                pr=_field(provenance, "pr", int, where),
                head=_field(provenance, "head", str, where),
                frozen=_field(provenance, "frozen", str, where),
            ),
            bundle=_bundle(_field(data, "bundle", dict, where), where),
        )

    if expected != "reject":
        raise EvalCaseError(f"{where}: a seeded-defect case is always expected to 'reject'")
    base_id = _field(data, "base", str, where)
    edit = _edit(data.get("edit"), where)
    base_path = path.with_name(f"{base_id}.json")
    if not base_path.is_file():
        raise EvalCaseError(f"{where}: its base {base_id!r} is not a case in this set")
    if _read(base_path).get("kind") != "accepted":
        raise EvalCaseError(f"{where}: its base {base_id!r} must be an accepted case")
    base = load_case(base_path)
    return EvalCase(
        id=case_id, kind=kind, expected=expected, check=check, reason=reason,
        provenance=base.provenance, bundle=_apply(base.bundle, edit, where),
        base=base_id, edit=edit,
    )


def dump_case(case: EvalCase) -> str:
    """The case as the text of its file."""
    data: dict[str, Any] = {"id": case.id, "kind": case.kind}
    if case.kind == "seeded-defect":
        data["base"] = case.base
    data["expected"] = case.expected
    if case.check is not None:
        data["check"] = case.check
    data["reason"] = case.reason
    if case.kind == "seeded-defect":
        data["edit"] = [{"in": r.where, "replace": r.find, "with": r.put} for r in case.edit]
    else:
        data["provenance"] = asdict(case.provenance)
        data["bundle"] = asdict(case.bundle)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _case_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.json"), key=lambda path: path.stem)


def load_set(directory: Path) -> tuple[EvalCase, ...]:
    """Every case in the directory, in a stable order."""
    return tuple(load_case(path) for path in _case_files(directory))


def set_fingerprint(directory: Path) -> str:
    """A short hash over every case file's name and bytes: it changes when a
    case is added, removed or edited, and two results are comparable only
    when it matches."""
    digest = hashlib.sha256()
    for path in _case_files(directory):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:12]
