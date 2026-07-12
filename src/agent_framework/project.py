"""Per-project configuration: what an adopted repo tells the framework.

One `agent-framework.toml` at the target root carries both the roster
(`[roles]`, parsed by `Roster.from_file`) and the `[project]` table read
here. Absent config means the framework's own documented defaults — the
behavior this repo had before portability — so adoption is opt-in per
knob. Malformed config fails loudly, naming the offending field (ADR
0002: Python is the harness's language; the target declares its own gate
and test conventions here).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import ProjectConfigError

CONFIG_FILE = "agent-framework.toml"

# The framework's own conventions — the pre-portability behavior, verbatim.
DEFAULT_GATE_COMMANDS = (
    "uv run ruff check .",
    "uv run mypy --strict",
    "uv run pytest",
    "uv run python scripts/check_spec_coverage.py --include-approved",
)
DEFAULT_TEST_PATTERN = r"^(?:async\s+)?def\s+(test_\w+)"


@dataclass(frozen=True)
class ProjectConfig:
    """The target project's contract with the framework's roles.

    An invalid `test_pattern` is unconstructible (validated here, not just
    in the loader) — a directly-constructed config reaching the gate must
    be as safe as a loaded one.
    """

    gate_commands: tuple[str, ...] = DEFAULT_GATE_COMMANDS
    conventions_note: str = ""
    test_pattern: str = DEFAULT_TEST_PATTERN  # exactly one capture group: the test name
    ignore_checks: tuple[str, ...] = ("validator",)

    def __post_init__(self) -> None:
        try:
            groups = re.compile(self.test_pattern).groups
        except re.error as e:
            raise ProjectConfigError(f"test_pattern is not a valid regex: {e}") from None
        if groups != 1:
            raise ProjectConfigError(
                "test_pattern must have exactly one capture group "
                f"(the test name), got {groups}"
            )


DEFAULTS = ProjectConfig()


def _string_tuple(raw: object, field: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise ProjectConfigError(f"[project] {field} must be a list of strings, got {raw!r}")
    return tuple(raw)


def load_project_config(root: Path = Path(".")) -> ProjectConfig:
    """Read `agent-framework.toml`'s `[project]` table; defaults when absent."""
    path = root / CONFIG_FILE
    if not path.is_file():
        return DEFAULTS
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ProjectConfigError(f"{path} is not valid TOML: {e}") from None
    table = data.get("project")
    if table is None:
        return DEFAULTS
    if not isinstance(table, dict):
        raise ProjectConfigError(f"{path}: [project] must be a table, got {table!r}")

    known = {"gate_commands", "conventions_note", "test_pattern", "ignore_checks"}
    unknown = set(table) - known
    if unknown:
        raise ProjectConfigError(
            f"{path}: unknown [project] field(s): {', '.join(sorted(unknown))}"
        )

    try:
        config = ProjectConfig(
            gate_commands=(
            _string_tuple(table["gate_commands"], "gate_commands")
                if "gate_commands" in table
                else DEFAULTS.gate_commands
            ),
            conventions_note=_as_str(table, "conventions_note", path),
            test_pattern=_as_str(table, "test_pattern", path) or DEFAULTS.test_pattern,
            ignore_checks=(
                _string_tuple(table["ignore_checks"], "ignore_checks")
                if "ignore_checks" in table
                else DEFAULTS.ignore_checks
            ),
        )
    except ProjectConfigError as e:
        raise ProjectConfigError(f"{path}: {e}") from None
    return config


def _as_str(table: dict[str, object], field: str, path: Path) -> str:
    raw = table.get(field, "")
    if not isinstance(raw, str):
        raise ProjectConfigError(f"{path}: [project] {field} must be a string, got {raw!r}")
    return raw
