"""The worker scorecard: the classes, the result file, show and compare.

Pure — code over recorded runs, no session and no git. A run's class
follows the plan's table; the reference tests are a separate value that
never changes it, and `could-not-run` is counted on its own, never as the
worker's success or failure (specs/worker-eval R-6..R-10, plan.md).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal, get_args

from ...errors import EvalResultError

Class = Literal[
    "ready", "gate-failed", "refused", "escalated",
    "timed-out", "spend-limit", "error", "could-not-run",
]
CLASSES: tuple[Class, ...] = get_args(Class)
ReferenceTests = Literal["passed", "failed", "not-run"]
REFERENCE_TESTS: tuple[ReferenceTests, ...] = get_args(ReferenceTests)
# How a session ended, before the eval scores it.
Ending = Literal["completed", "escalated", "timed-out", "spend-limit", "error"]


@dataclass(frozen=True)
class GateCommand:
    command: str
    passed: bool


def classify(ending: Ending, gate: tuple[GateCommand, ...], handoff: tuple[str, ...]) -> Class:
    """The plan's class table. A completed session is `ready` when every
    gate command passed and the handoff check found nothing."""
    if ending != "completed":
        return ending
    if not all(g.passed for g in gate):
        return "gate-failed"
    return "refused" if handoff else "ready"


@dataclass(frozen=True)
class Kept:
    """Where a run's working files are kept; None when there is none."""

    record: str | None = None  # the session record
    diff: str | None = None  # the session's patch
    gate: str | None = None  # the gate commands' output


@dataclass(frozen=True)
class RunRecord:
    """One run of one case."""

    case: str
    run: int
    cls: Class
    reference_tests: ReferenceTests = "not-run"
    gate: tuple[GateCommand, ...] = ()
    handoff: tuple[str, ...] = ()  # the handoff check's findings
    diff_lines: int | None = None
    cost_usd: float | None = None  # as the session record reports it
    turns: int | None = None
    elapsed_s: float | None = None
    kept: Kept = Kept()
    detail: str = ""  # why it errored or could not run


# ---- the scorecard ------------------------------------------------------------


@dataclass(frozen=True)
class Counts:
    classes: dict[str, int]
    reference_tests: dict[str, int]


@dataclass(frozen=True)
class Spread:
    total: float
    median: float | None
    reported: int  # how many runs the numbers are over


@dataclass(frozen=True)
class Scorecard:
    total: Counts
    cases: dict[str, Counts]
    cost_usd: Spread
    elapsed_s: Spread  # over the runs that ran: never a could-not-run
    unstable: tuple[str, ...]  # cases whose runs landed in different classes


def _counts(runs: list[RunRecord]) -> Counts:
    classes, tests = Counter(r.cls for r in runs), Counter(r.reference_tests for r in runs)
    return Counts({c: classes[c] for c in CLASSES}, {t: tests[t] for t in REFERENCE_TESTS})


def _spread(values: list[float]) -> Spread:
    return Spread(sum(values), statistics.median(values) if values else None, len(values))


def scorecard(results: tuple[RunRecord, ...]) -> Scorecard:
    by_case: dict[str, list[RunRecord]] = {}
    for r in sorted(results, key=lambda r: (r.case, r.run)):
        by_case.setdefault(r.case, []).append(r)
    ran = [r for r in results if r.cls != "could-not-run"]
    return Scorecard(
        total=_counts(list(results)),
        cases={case: _counts(runs) for case, runs in by_case.items()},
        cost_usd=_spread([r.cost_usd for r in ran if r.cost_usd is not None]),
        elapsed_s=_spread([r.elapsed_s for r in ran if r.elapsed_s is not None]),
        unstable=tuple(c for c, runs in by_case.items() if len({r.cls for r in runs}) > 1),
    )


# ---- the result file ----------------------------------------------------------


@dataclass(frozen=True)
class Result:
    """One run of the worker eval, and what it measured."""

    model: str  # the worker's binding in the roster, provider:model
    claude_code: str
    date: str
    runs: int
    time_budget_s: int
    spend_limit_usd: float
    case_set: str  # the case-set fingerprint
    briefs: dict[str, str]  # case id -> fingerprint of the brief it was given
    results: tuple[RunRecord, ...]

    @property
    def scorecard(self) -> Scorecard:
        return scorecard(self.results)


def _run_json(r: RunRecord) -> dict[str, Any]:
    item = asdict(r)
    return {"case": item.pop("case"), "run": item.pop("run"), "class": item.pop("cls")} | item


def result_to_json(result: Result) -> str:
    data = asdict(result)
    data["results"] = [_run_json(r) for r in result.results]
    data["scorecard"] = asdict(result.scorecard)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _run_from(j: dict[str, Any]) -> RunRecord:
    if j["class"] not in CLASSES or j["reference_tests"] not in REFERENCE_TESTS:
        raise ValueError(f"unknown class or reference-test value in {j['case']} run {j['run']}")
    return RunRecord(
        case=str(j["case"]), run=int(j["run"]), cls=j["class"],
        reference_tests=j["reference_tests"],
        gate=tuple(GateCommand(str(g["command"]), bool(g["passed"])) for g in j["gate"]),
        handoff=tuple(str(f) for f in j["handoff"]),
        diff_lines=j["diff_lines"], cost_usd=j["cost_usd"], turns=j["turns"],
        elapsed_s=j["elapsed_s"], kept=Kept(**j["kept"]), detail=str(j["detail"]),
    )


def result_from_json(text: str) -> Result:
    """Read a result file. Its scorecard is derived, so it is recomputed
    from the runs rather than trusted."""
    try:
        data: Any = json.loads(text)
        return Result(
            model=str(data["model"]), claude_code=str(data["claude_code"]),
            date=str(data["date"]), runs=int(data["runs"]),
            time_budget_s=int(data["time_budget_s"]),
            spend_limit_usd=float(data["spend_limit_usd"]),
            case_set=str(data["case_set"]),
            briefs={str(k): str(v) for k, v in data["briefs"].items()},
            results=tuple(_run_from(j) for j in data["results"]),
        )
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise EvalResultError(f"not a worker eval result: {type(e).__name__}: {e}") from None


# ---- show and compare ---------------------------------------------------------


def _head(r: Result) -> str:
    return (
        f"{r.model}, Claude Code {r.claude_code}, {r.date}, {r.runs} run(s) per case, "
        f"time budget {r.time_budget_s} s, spend limit ${r.spend_limit_usd:.2f}, "
        f"case set {r.case_set}"
    )


def _count_line(c: Counts) -> str:
    classes = ", ".join(f"{k} {v}" for k, v in c.classes.items() if v)
    tests = ", ".join(f"{k} {v}" for k, v in c.reference_tests.items() if v)
    return f"{classes or 'no runs'}; reference tests: {tests or 'none'}"


def _spread_line(name: str, s: Spread, unit: str) -> str:
    median = "-" if s.median is None else f"{s.median:.2f}"
    return f"{name}: total {s.total:.2f}{unit}, median {median}{unit} over {s.reported} run(s)"


def _listed(title: str, runs: list[RunRecord]) -> list[str]:
    lines = [f"{title} ({len(runs)}):"]
    for r in runs:
        why = f" — {r.detail}" if r.detail else ""
        lines.append(f"  {r.case} run {r.run}: {r.cls}, reference tests {r.reference_tests}{why}")
        for label, path in (("session record", r.kept.record), ("diff", r.kept.diff),
                            ("gate output", r.kept.gate)):
            lines.append(f"    {label}: {path or '(none kept)'}")
    return lines


def render(result: Result) -> str:
    """The scorecard, then every run not ready for review and every
    reference-test failure, with where its files are kept."""
    card = result.scorecard
    total = len(result.results)
    lines = [
        _head(result), "",
        (f"ready for review: {card.total.classes['ready']} of {total} run(s); "
         f"reference tests passed: {card.total.reference_tests['passed']}; "
         f"could not run: {card.total.classes['could-not-run']}"),
        f"total — {_count_line(card.total)}",
        _spread_line("reported cost", card.cost_usd, " USD"),
        _spread_line("elapsed", card.elapsed_s, " s"), "",
    ]
    for case, counts in card.cases.items():
        mark = "  [unstable]" if case in card.unstable else ""
        lines.append(f"{case}: {_count_line(counts)}{mark}")
    lines.append("")
    lines += _listed("Not ready for review", [r for r in result.results if r.cls != "ready"])
    lines += _listed(
        "Reference-test failures", [r for r in result.results if r.reference_tests == "failed"]
    )
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Change:
    case: str
    before: tuple[tuple[Class, ReferenceTests], ...]  # one per run
    after: tuple[tuple[Class, ReferenceTests], ...]


def _by_case(result: Result) -> dict[str, tuple[tuple[Class, ReferenceTests], ...]]:
    seen: dict[str, list[tuple[Class, ReferenceTests]]] = {}
    for r in sorted(result.results, key=lambda r: (r.case, r.run)):
        seen.setdefault(r.case, []).append((r.cls, r.reference_tests))
    return {case: tuple(runs) for case, runs in seen.items()}


def comparable(before: Result, after: Result) -> bool:
    return before.case_set == after.case_set


def compare(before: Result, after: Result) -> tuple[Change, ...]:
    """The cases, run in both, whose class or reference-test result changed."""
    was, now = _by_case(before), _by_case(after)
    return tuple(
        Change(case, was[case], now[case])
        for case in sorted(was.keys() & now.keys()) if was[case] != now[case]
    )


def render_comparison(before: Result, after: Result) -> str:
    lines = [f"before: {_head(before)}", f"after:  {_head(after)}", ""]
    if not comparable(before, after):
        lines.append(
            "These results are not comparable: their case sets differ "
            f"({before.case_set} and {after.case_set})."
        )
        return "\n".join(lines) + "\n"
    for label, result in (("before", before), ("after", after)):
        lines.append(f"{label} — {_count_line(result.scorecard.total)}")
    lines.append("")
    changes = compare(before, after)
    if not changes:
        lines.append("No case changed class or reference-test result.")

    def runs(seen: tuple[tuple[Class, ReferenceTests], ...]) -> str:
        return ", ".join(f"{cls} (reference tests {tests})" for cls, tests in seen)

    for change in changes:
        lines.append(f"{change.case}: {runs(change.before)} → {runs(change.after)}")
    return "\n".join(lines) + "\n"
