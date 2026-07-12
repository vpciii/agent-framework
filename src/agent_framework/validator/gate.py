"""The cite-the-test gate: deterministic checks, then (only then) judgment.

The single entry point of the validator core. Findings from the
deterministic stage reject without a model call (ADR 0005); a clean bundle
gets exactly one judgment dispatch through the roster's validator role; a
clean judgment yields a PASS whose citations come from the deterministic
evidence — `Pass.from_evidence` makes an uncited criterion unconstructible.
"""

from __future__ import annotations

import logging
import re

from ..project import DEFAULTS, ProjectConfig
from ..providers.registry import ProviderRegistry
from ..roster import Roster
from .bundle import EvidenceBundle
from .checks import citations_for_pass, run_checks
from .judgment import judge
from .verdict import Pass, Reject, Verdict

logger = logging.getLogger(__name__)


async def validate(
    bundle: EvidenceBundle,
    roster: Roster,
    *,
    registry: ProviderRegistry | None = None,
    project: ProjectConfig = DEFAULTS,
) -> Verdict:
    """Gate one task's PR evidence; the verdict cites, it never asserts."""
    task_id = bundle.task.task_id
    pattern = re.compile(project.test_pattern, re.M)

    findings = run_checks(bundle, pattern)
    if findings:
        logger.info(
            "gate %s: REJECT at deterministic stage (%d findings, no model call)",
            task_id,
            len(findings),
        )
        return Reject(task_id=task_id, findings=findings)

    judgment = await judge(bundle, roster, registry=registry)
    if judgment.defect_found:
        logger.info(
            "gate %s: REJECT at judgment stage (%d findings)",
            task_id,
            len(judgment.findings),
        )
        return Reject(task_id=task_id, findings=judgment.findings)

    verdict = Pass.from_evidence(
        bundle.task, citations_for_pass(bundle, pattern), ci=bundle.ci.summary
    )
    logger.info("gate %s: PASS (%d criteria cited)", task_id, len(verdict.citations))
    return verdict
