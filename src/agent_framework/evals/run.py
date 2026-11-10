"""The eval run: the gate's own judgment, made once per case and recorded.

Nothing about the judgment is copied here. Each case goes through
`validator.judgment.judge` — the same request, tool, parsing and quote check
the gate uses — so the eval cannot drift from the gate. What `judge` does
not return (the token counts, and how many findings the model reported
before the quote check dropped some) is read from the provider's response
by wrapping the roster's validator adapter in a recorder, inside a registry
of the run's own. No line of the gate changes (specs/validator-eval-set).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ..errors import JudgmentFormatError, NoVerdictError, ProviderError
from ..providers.base import Provider, Request, Response
from ..providers.registry import ProviderRegistry, default_registry
from ..roster import Roster
from ..validator.judgment import VERDICT_TOOL, judge
from .case import EvalCase
from .scorecard import JudgmentRecord, NotJudged, Outcome, Passed, Rejected, record


class _Recorder:
    """The validator's adapter, keeping the response to the latest request."""

    def __init__(self, inner: Provider) -> None:
        self._inner = inner
        self.last: Response | None = None

    async def invoke(self, request: Request, *, model: str) -> Response:
        self.last = None  # a failed call leaves nothing of the one before it
        self.last = await self._inner.invoke(request, model=model)
        return self.last


def _reported(response: Response | None) -> int:
    """How many findings the model reported with a defect, before any was dropped."""
    if response is None:
        return 0
    call = next((c for c in response.tool_calls if c.name == VERDICT_TOOL.name), None)
    if call is None or not call.arguments.get("defect_found"):
        return 0
    findings = call.arguments.get("findings")
    return len(findings) if isinstance(findings, list) else 0


async def _judge(case: EvalCase, roster: Roster, registry: ProviderRegistry) -> Outcome:
    """One judgment; every way it cannot be made is named as the gate's CLI names it."""
    try:
        judgment = await judge(case.bundle, roster, registry=registry)
    except NoVerdictError as e:
        return NotJudged(e.reason)
    except JudgmentFormatError:
        return NotJudged("malformed")
    except ProviderError:
        return NotJudged("provider-error")
    return Rejected(judgment.findings) if judgment.defect_found else Passed()


async def run_eval(
    cases: tuple[EvalCase, ...],
    roster: Roster,
    *,
    registry: ProviderRegistry | None = None,
    runs: int = 1,
    pause: float = 0.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_judgment: Callable[[JudgmentRecord], None] | None = None,
) -> tuple[JudgmentRecord, ...]:
    """Judge every case `runs` times through the roster's validator role.

    A failure on one case — a provider error, a rate limit, an answer that
    cannot be read — is that case's could-not-judge, and the run goes on.
    `pause` seconds are slept between judgments, never after the last.
    """
    source = registry if registry is not None else default_registry()
    validator = roster.resolve("validator")
    recorder = _Recorder(source.get(validator.provider))
    own = ProviderRegistry()
    own.register(validator.provider, recorder)

    judged: list[JudgmentRecord] = []
    total = runs * len(cases)
    for run in range(1, runs + 1):
        for case in cases:
            recorder.last = None
            outcome = await _judge(case, roster, own)
            usage = recorder.last.usage if recorder.last is not None else None
            item = record(
                case, run, outcome,
                reported=_reported(recorder.last),
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
            )
            judged.append(item)
            if on_judgment is not None:
                on_judgment(item)
            if pause > 0 and len(judged) < total:
                await sleep(pause)
    return tuple(judged)
