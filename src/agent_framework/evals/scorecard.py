"""Scoring an eval run: the classes, the scorecard, a comparable result.

Pure. Every score is computed here by code from a case's expected outcome
and the judgment's actual one — no model grades anything. "Could not
judge" is its own class and is never counted as right or as wrong
(specs/validator-eval-set, plan.md).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

from ..errors import EvalResultError
from ..validator import judgment
from ..validator.bundle import CIEvidence, Contract, EvidenceBundle, TaskRef
from ..validator.verdict import Finding
from .case import EvalCase, Expected

Class = Literal[
    "passed", "wrongly-rejected", "caught", "other-reason", "missed", "could-not-judge"
]
ACCEPTED_CLASSES: tuple[Class, ...] = ("passed", "wrongly-rejected", "could-not-judge")
SEEDED_CLASSES: tuple[Class, ...] = ("caught", "other-reason", "missed", "could-not-judge")


@dataclass(frozen=True)
class Passed:
    """The judgment reported no defect."""


@dataclass(frozen=True)
class Rejected:
    """The judgment reported a defect; these are its supported findings."""

    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class NotJudged:
    """The judgment could not be made; `reason` as the gate's CLI names it."""

    reason: str


Outcome = Passed | Rejected | NotJudged


def classify(case: EvalCase, outcome: Outcome) -> Class:
    """The class of one judgment. Scoring follows the case's expected
    outcome, so an accepted case re-labelled `reject` is scored as a defect."""
    if isinstance(outcome, NotJudged):
        return "could-not-judge"
    if case.expected == "pass":
        return "passed" if isinstance(outcome, Passed) else "wrongly-rejected"
    if isinstance(outcome, Passed):
        return "missed"
    under_its_item = any(f.check == case.check for f in outcome.findings)
    return "caught" if under_its_item else "other-reason"


@dataclass(frozen=True)
class JudgmentRecord:
    """One judgment of one case, as a result file keeps it."""

    case: str
    run: int
    expected: Expected
    check: str | None  # the checklist item a `reject` case's defect falls under
    cls: Class
    outcome: Literal["pass", "reject", "none"]
    reason: str | None  # why it could not be judged
    findings: tuple[Finding, ...]
    reported: int  # findings the model reported, before the quote check
    dropped: int  # of those, dropped as unsupported
    input_tokens: int | None
    output_tokens: int | None


def record(
    case: EvalCase,
    run: int,
    outcome: Outcome,
    *,
    reported: int,
    input_tokens: int | None,
    output_tokens: int | None,
) -> JudgmentRecord:
    """Score one judgment and put it in the shape a result keeps."""
    findings: tuple[Finding, ...] = ()
    reason: str | None = None
    kind: Literal["pass", "reject", "none"] = "pass"
    dropped = 0
    if isinstance(outcome, Rejected):
        kind, findings = "reject", outcome.findings
        dropped = max(reported - len(findings), 0)
    elif isinstance(outcome, NotJudged):
        kind, reason = "none", outcome.reason
        # Every reported finding was dropped, which is why there is no verdict.
        dropped = reported if outcome.reason == "unsupported-finding" else 0
    return JudgmentRecord(
        case=case.id, run=run, expected=case.expected, check=case.check,
        cls=classify(case, outcome), outcome=kind, reason=reason, findings=findings,
        reported=reported, dropped=dropped,
        input_tokens=input_tokens, output_tokens=output_tokens,
    )


@dataclass(frozen=True)
class Scorecard:
    """Counts of judgments by class, per kind of case."""

    accepted: dict[str, int]  # cases expected to pass
    seeded: dict[str, int]  # cases expected to be rejected
    dropped: int
    input_tokens: int
    output_tokens: int
    unstable: tuple[str, ...]  # cases whose runs disagree


def scorecard(judgments: tuple[JudgmentRecord, ...]) -> Scorecard:
    accepted = Counter(j.cls for j in judgments if j.expected == "pass")
    seeded = Counter(j.cls for j in judgments if j.expected == "reject")
    classes: dict[str, set[str]] = {}
    for j in judgments:
        classes.setdefault(j.case, set()).add(j.cls)
    return Scorecard(
        accepted={c: accepted[c] for c in ACCEPTED_CLASSES},
        seeded={c: seeded[c] for c in SEEDED_CLASSES},
        dropped=sum(j.dropped for j in judgments),
        input_tokens=sum(j.input_tokens or 0 for j in judgments),
        output_tokens=sum(j.output_tokens or 0 for j in judgments),
        unstable=tuple(sorted(case for case, seen in classes.items() if len(seen) > 1)),
    )


@dataclass(frozen=True)
class Result:
    """One run of the eval, and what it measured."""

    model: str
    date: str
    runs: int
    instructions: str  # fingerprint of the judgment's instructions and schema
    case_set: str  # fingerprint of the case set
    judgments: tuple[JudgmentRecord, ...]

    @property
    def scorecard(self) -> Scorecard:
        return scorecard(self.judgments)


# A fixed placeholder that fills every section of the request, so a change
# to the wording or to the layout of any of them moves the fingerprint —
# and no case can.
_PLACEHOLDER = EvidenceBundle(
    task=TaskRef(task_id="T-0", criteria=("SC-0",), is_fix=True),
    diff="(diff)",
    tests={"tests/placeholder.py": "(test)"},
    ci=CIEvidence(green=True, summary="(ci)"),
    red_evidence="(red)",
    contract=Contract(
        spec_slug="placeholder", criterion_texts={"SC-0": "(criterion)"},
        task_block="(task)", cited_tests={"SC-0": ("tests/placeholder.py::test",)},
        ref="0000000",
    ),
)


def instructions_fingerprint() -> str:
    """A short hash of the request the judgment would make — its wording,
    the layout of what it is sent, and its tool's schema — with the data
    held fixed."""
    request = judgment.build_request(_PLACEHOLDER)
    payload = json.dumps(
        {
            "prompt": request.prompt,
            "require_tool": request.require_tool,
            "max_output_tokens": request.max_output_tokens,
            "tools": [asdict(tool) for tool in request.tools],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


# ---- the result file ------------------------------------------------------


def result_to_json(result: Result) -> str:
    judgments = []
    for j in result.judgments:
        item = asdict(j)
        item["class"] = item.pop("cls")
        judgments.append(item)
    data = {
        "model": result.model, "date": result.date, "runs": result.runs,
        "instructions": result.instructions, "case_set": result.case_set,
        "scorecard": asdict(result.scorecard),
        "judgments": judgments,
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def result_from_json(text: str) -> Result:
    """Read a result file. The scorecard in it is derived, so it is
    recomputed from the judgments rather than trusted."""
    try:
        data: Any = json.loads(text)
        return Result(
            model=str(data["model"]), date=str(data["date"]), runs=int(data["runs"]),
            instructions=str(data["instructions"]), case_set=str(data["case_set"]),
            judgments=tuple(
                JudgmentRecord(
                    case=str(j["case"]), run=int(j["run"]), expected=j["expected"],
                    check=j["check"], cls=j["class"], outcome=j["outcome"],
                    reason=j["reason"],
                    findings=tuple(
                        Finding(check=str(f["check"]), finding=str(f["finding"]),
                                evidence=str(f["evidence"]))
                        for f in j["findings"]
                    ),
                    reported=int(j["reported"]), dropped=int(j["dropped"]),
                    input_tokens=j["input_tokens"], output_tokens=j["output_tokens"],
                )
                for j in data["judgments"]
            ),
        )
    except (ValueError, KeyError, TypeError) as e:
        raise EvalResultError(f"not an eval result: {type(e).__name__}: {e}") from None


# ---- rendering ------------------------------------------------------------

_LABELS: dict[str, str] = {
    "passed": "passed", "wrongly-rejected": "wrongly rejected", "caught": "caught",
    "other-reason": "other reason", "missed": "missed",
}


def _counts(title: str, counts: dict[str, int]) -> list[str]:
    """One kind of case: each class beside the number judged, never a bare rate."""
    judged = sum(n for cls, n in counts.items() if cls != "could-not-judge")
    lines = [f"{title}: {sum(counts.values())} judgments"]
    for cls, n in counts.items():
        if cls == "could-not-judge":
            lines.append(f"  {'could not judge':<18}{n}")
            continue
        rate = f" ({round(100 * n / judged)}%)" if judged else ""
        lines.append(f"  {_LABELS[cls]:<18}{n} of {judged} judged{rate}")
    return lines


def _name(j: JudgmentRecord, runs: int) -> str:
    return j.case if runs == 1 else f"{j.case} (run {j.run})"


def _findings(j: JudgmentRecord) -> list[str]:
    lines: list[str] = []
    for f in j.findings:
        lines.append(f"    [{f.check}] {f.finding}")
        lines.extend(f"      {line}" for line in f.evidence.splitlines())
    return lines


def _head(result: Result) -> str:
    return (
        f"{result.model}, {result.date} · instructions {result.instructions} · "
        f"case set {result.case_set} · {result.runs} run(s) per case"
    )


def render(result: Result) -> str:
    """The scorecard as text, and every case a human should look at."""
    card = result.scorecard
    lines = ["Eval of the validator's judgment", _head(result), ""]
    lines += _counts("Accepted work (expected PASS)", card.accepted)
    lines += _counts("Defects (expected REJECT)", card.seeded)
    lines += [
        f"Unsupported findings dropped: {card.dropped}",
        f"Tokens: {card.input_tokens:,} in, {card.output_tokens:,} out",
    ]

    def of(cls: Class) -> list[JudgmentRecord]:
        return [j for j in result.judgments if j.cls == cls]

    if wrongly := of("wrongly-rejected"):
        lines += ["", "Wrongly rejected — is the judgment wrong, or the case's answer?"]
        for j in wrongly:
            lines += [f"  {_name(j, result.runs)}", *_findings(j)]
    if missed := of("missed"):
        lines += ["", "Missed"]
        lines += [
            f"  {_name(j, result.runs)} — expected a REJECT under {j.check}; "
            "the judgment passed it"
            for j in missed
        ]
    if other := of("other-reason"):
        lines += ["", "Rejected for another reason"]
        for j in other:
            lines += [f"  {_name(j, result.runs)} — expected under {j.check}", *_findings(j)]
    if holes := of("could-not-judge"):
        lines += ["", "Could not judge"]
        lines += [f"  {_name(j, result.runs)}: {j.reason}" for j in holes]
    if card.unstable:
        lines += ["", "Unstable (runs disagree): " + ", ".join(card.unstable)]
    return "\n".join(lines) + "\n"


# ---- comparing two results ------------------------------------------------


@dataclass(frozen=True)
class Change:
    case: str
    before: tuple[Class, ...]  # one class per run
    after: tuple[Class, ...]


@dataclass(frozen=True)
class Comparison:
    comparable: bool
    changed: tuple[Change, ...]  # among the cases both results judged
    only_before: tuple[str, ...] = ()  # judged in one result only: not compared
    only_after: tuple[str, ...] = ()


def _by_case(result: Result) -> dict[str, tuple[Class, ...]]:
    classes: dict[str, list[Class]] = {}
    for j in sorted(result.judgments, key=lambda j: (j.case, j.run)):
        classes.setdefault(j.case, []).append(j.cls)
    return {case: tuple(seen) for case, seen in classes.items()}


def compare(before: Result, after: Result) -> Comparison:
    """The cases whose class changed between two results on the same case
    set. Results on different case sets are not comparable, and no
    difference between them is offered.

    A run of some cases (`--only`) carries the whole set's fingerprint, so
    two results on one set need not have judged the same cases. Only a case
    both judged can have changed; one judged in a single result is named as
    such and never counted as a change."""
    if before.case_set != after.case_set:
        return Comparison(comparable=False, changed=())
    was, now = _by_case(before), _by_case(after)
    return Comparison(
        comparable=True,
        changed=tuple(
            Change(case=case, before=was[case], after=now[case])
            for case in sorted(was.keys() & now.keys())
            if was[case] != now[case]
        ),
        only_before=tuple(sorted(was.keys() - now.keys())),
        only_after=tuple(sorted(now.keys() - was.keys())),
    )


def render_comparison(before: Result, after: Result) -> str:
    lines = [f"before: {_head(before)}", f"after:  {_head(after)}", ""]
    comparison = compare(before, after)
    if not comparison.comparable:
        lines.append(
            f"These results are not comparable: their case sets differ "
            f"({before.case_set} and {after.case_set})."
        )
        return "\n".join(lines) + "\n"
    for label, result in (("before", before), ("after", after)):
        card = result.scorecard
        lines += _counts(f"{label} — accepted work (expected PASS)", card.accepted)
        lines += _counts(f"{label} — defects (expected REJECT)", card.seeded)
    lines.append("")
    partial = bool(comparison.only_before or comparison.only_after)
    if not comparison.changed:
        lines.append(
            "No case judged in both results changed class." if partial
            else "No case changed class."
        )
    for change in comparison.changed:
        lines.append(f"{change.case}: {', '.join(change.before)} → {', '.join(change.after)}")
    for label, only in (("before", comparison.only_before), ("after", comparison.only_after)):
        if only:
            lines.append(
                f"Judged only in the {label} result ({len(only)}), not compared: "
                f"{', '.join(only)}"
            )
    return "\n".join(lines) + "\n"
