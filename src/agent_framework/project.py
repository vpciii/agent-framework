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
DEFAULT_TEST_PATHS = ("tests/**/*.py",)


def _path_regex(pattern: str) -> re.Pattern[str]:
    """A path pattern as a regex over a repo-relative POSIX path:
    `**/` spans zero or more directories, `*` and `?` stay within one."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out)


def path_matches(path: str, patterns: tuple[str, ...]) -> bool:
    """Whether a repo-relative path matches any of a project's path patterns
    (`test_paths`, `protected_paths`)."""
    return any(_path_regex(p).fullmatch(path) for p in patterns)


DEFAULT_PROTECTED_PATHS = (".github/**", "agent-framework.toml")

_HOST_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_HOST_RE = re.compile(rf"{_HOST_LABEL}(?:\.{_HOST_LABEL})*")
_ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _is_session_path(entry: str) -> bool:
    """Absolute or under the home directory, with no `..` — a path the
    sandbox can be told about without depending on where it is launched."""
    return entry.startswith(("/", "~/")) and ".." not in entry.split("/")


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
    # Which changed files the validator collects as tests (path patterns).
    test_paths: tuple[str, ...] = DEFAULT_TEST_PATHS
    # How far the worker session's confinement profile is widened (ADR 0007):
    # nothing beyond the worktree, the repository and no network unless named.
    session_write_paths: tuple[str, ...] = ()
    session_read_paths: tuple[str, ...] = ()
    session_network: tuple[str, ...] = ()  # host names a command may reach
    session_env: tuple[str, ...] = ()  # variable names passed to the session
    # Paths a session's diff may not change (the handoff check; path patterns).
    protected_paths: tuple[str, ...] = DEFAULT_PROTECTED_PATHS

    def __post_init__(self) -> None:
        for field in ("test_paths", "protected_paths"):
            value = getattr(self, field)
            if not all(isinstance(p, str) and p.strip() for p in value):
                raise ProjectConfigError(
                    f"{field} must be non-empty path patterns, got {value!r}"
                )
        for field in ("session_write_paths", "session_read_paths"):
            for entry in getattr(self, field):
                if not _is_session_path(entry):
                    raise ProjectConfigError(
                        f"{field} entries must be absolute or start with ~/ "
                        f"(and contain no ..), got {entry!r}"
                    )
        for entry in self.session_network:
            if not _HOST_RE.fullmatch(entry):
                raise ProjectConfigError(
                    "session_network entries must be bare host names "
                    f"(no scheme, path or port), got {entry!r}"
                )
        for entry in self.session_env:
            if not _ENV_NAME_RE.fullmatch(entry):
                raise ProjectConfigError(
                    f"session_env entries must be variable names, got {entry!r}"
                )
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

    list_fields = (
        "gate_commands", "ignore_checks", "test_paths", "session_write_paths",
        "session_read_paths", "session_network", "session_env", "protected_paths",
    )
    known = {"conventions_note", "test_pattern", *list_fields}
    unknown = set(table) - known
    if unknown:
        raise ProjectConfigError(
            f"{path}: unknown [project] field(s): {', '.join(sorted(unknown))}"
        )

    try:
        lists = {
            field: _string_tuple(table[field], field) for field in list_fields if field in table
        }
        config = ProjectConfig(
            conventions_note=_as_str(table, "conventions_note", path),
            # Only an absent field means the default: an explicit value, the
            # empty string included, is validated as given.
            test_pattern=(
                _as_str(table, "test_pattern", path)
                if "test_pattern" in table
                else DEFAULTS.test_pattern
            ),
            **lists,
        )
    except ProjectConfigError as e:
        raise ProjectConfigError(f"{path}: {e}") from None
    return config


def _as_str(table: dict[str, object], field: str, path: Path) -> str:
    raw = table.get(field, "")
    if not isinstance(raw, str):
        raise ProjectConfigError(f"{path}: [project] {field} must be a string, got {raw!r}")
    return raw
