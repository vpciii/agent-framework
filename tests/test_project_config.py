"""Per-project configuration loading.

Verifies SC-1: full parse of all four fields; missing file or table →
the documented defaults; malformed config → ProjectConfigError naming
the offending field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_framework.errors import ProjectConfigError
from agent_framework.project import DEFAULTS, load_project_config


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / "agent-framework.toml").write_text(body, encoding="utf-8")
    return tmp_path


def test_sc1_full_config_parses_all_four_fields(tmp_path: Path) -> None:
    """SC-1: a target-root config parses into the project-config value."""
    root = _write(
        tmp_path,
        """
[roles]
worker = { provider = "anthropic", model = "m" }

[project]
gate_commands = ["uv run pytest", "docker build -t opn-mcp-ci ."]
conventions_note = "Read CLAUDE.md; single-source prompts (ADR 0008)."
test_pattern = 'it\\("(test[A-Za-z ]+)"'
ignore_checks = ["validator", "claude-review"]
""",
    )
    config = load_project_config(root)
    assert config.gate_commands == ("uv run pytest", "docker build -t opn-mcp-ci .")
    assert "ADR 0008" in config.conventions_note
    assert config.ignore_checks == ("validator", "claude-review")
    assert config.test_pattern == 'it\\("(test[A-Za-z ]+)"'  # a Jest-shaped pattern


def test_sc1_missing_file_and_missing_table_yield_defaults(tmp_path: Path) -> None:
    """SC-1: absent config means the framework's documented defaults."""
    assert load_project_config(tmp_path) == DEFAULTS  # no file at all
    root = _write(tmp_path, '[roles]\nworker = { provider = "a", model = "m" }\n')
    assert load_project_config(root) == DEFAULTS  # file without [project]


def test_sc1_partial_config_keeps_defaults_for_omitted_fields(tmp_path: Path) -> None:
    root = _write(tmp_path, '[project]\ngate_commands = ["make test"]\n')
    config = load_project_config(root)
    assert config.gate_commands == ("make test",)
    assert config.test_pattern == DEFAULTS.test_pattern
    assert config.ignore_checks == DEFAULTS.ignore_checks


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("[project\nbroken", "not valid TOML"),
        ('[project]\ngate_commands = "not-a-list"\n', "gate_commands must be a list"),
        ('[project]\nconventions_note = 7\n', "conventions_note must be a string"),
        ('[project]\ntest_pattern = "(unclosed"\n', "not a valid regex"),
        ('[project]\ntest_pattern = "no_capture_group"\n', "exactly one capture group"),
        ('[project]\ntest_pattern = "(a)(b)"\n', "exactly one capture group"),
        ('[project]\nsurprise_field = 1\n', "unknown .project. field"),
    ],
)
def test_sc1_malformed_config_fails_loudly_naming_the_problem(
    tmp_path: Path, body: str, match: str
) -> None:
    """SC-1: no silent misconfiguration — the error names the offending field."""
    root = _write(tmp_path, body)
    with pytest.raises(ProjectConfigError, match=match):
        load_project_config(root)


def test_defaults_reproduce_the_framework_gate() -> None:
    """The documented defaults ARE the pre-portability behavior."""
    assert "uv run pytest" in DEFAULTS.gate_commands
    assert any("mypy --strict" in c for c in DEFAULTS.gate_commands)
    assert DEFAULTS.ignore_checks == ("validator",)


def test_invalid_pattern_is_unconstructible_even_programmatically() -> None:
    """Regression (#40 advisory REJECT, a live Gemini finding): a directly
    constructed ProjectConfig bypassed the loader's pattern validation, so
    validate(project=...) could crash with a raw IndexError during citation
    scanning. Invalid patterns are now unconstructible — by construction."""
    from agent_framework.project import ProjectConfig

    with pytest.raises(ProjectConfigError, match="exactly one capture group"):
        ProjectConfig(test_pattern="test_no_group")
    with pytest.raises(ProjectConfigError, match="not a valid regex"):
        ProjectConfig(test_pattern="(unclosed")


# --- specs/worker-confinement SC-8: the confinement profile's and the
# --- handoff check's config fields.

_CONFINEMENT_FIELDS = (
    "session_write_paths", "session_read_paths", "session_network", "session_env",
)


def test_sc8_confinement_fields_parse_when_well_formed(tmp_path: Path) -> None:
    """SC-8 (worker-confinement): each new field parses into the config value."""
    root = _write(
        tmp_path,
        """
[project]
session_write_paths = ["~/.cache/uv", "/var/cache/build"]
session_read_paths = ["~/.local/share/uv"]
session_network = ["pypi.org", "files.pythonhosted.org"]
session_env = ["UV_INDEX_URL", "CI"]
protected_paths = [".github/**", "agent-framework.toml", "infra/**"]
""",
    )
    config = load_project_config(root)
    assert config.session_write_paths == ("~/.cache/uv", "/var/cache/build")
    assert config.session_read_paths == ("~/.local/share/uv",)
    assert config.session_network == ("pypi.org", "files.pythonhosted.org")
    assert config.session_env == ("UV_INDEX_URL", "CI")
    assert config.protected_paths == (".github/**", "agent-framework.toml", "infra/**")


def test_sc8_absent_confinement_fields_take_their_documented_defaults(tmp_path: Path) -> None:
    """SC-8 (worker-confinement): nothing is widened unless the project says so."""
    config = load_project_config(_write(tmp_path, '[project]\ngate_commands = ["make test"]\n'))
    for field in _CONFINEMENT_FIELDS:
        assert getattr(config, field) == (), field
    assert config.protected_paths == (".github/**", "agent-framework.toml")
    assert DEFAULTS.protected_paths == config.protected_paths


@pytest.mark.parametrize(
    ("field", "value"),
    [
        # A string where a list belongs.
        ("session_write_paths", '"~/.cache/uv"'),
        ("session_network", '"pypi.org"'),
        ("protected_paths", '".github/**"'),
        # An empty entry.
        ("session_write_paths", '["~/.cache/uv", ""]'),
        ("session_read_paths", '[""]'),
        ("session_network", '["pypi.org", " "]'),
        ("session_env", '[""]'),
        ("protected_paths", '[""]'),
        # A path that is neither absolute nor under the home directory.
        ("session_write_paths", '["cache/uv"]'),
        ("session_read_paths", '["../elsewhere"]'),
        # A host given as a URL, with a path, or with a port.
        ("session_network", '["https://pypi.org"]'),
        ("session_network", '["pypi.org/simple"]'),
        ("session_network", '["pypi.org:443"]'),
        # Not a variable name.
        ("session_env", '["UV INDEX"]'),
        ("session_env", '["A=b"]'),
    ],
)
def test_sc8_malformed_confinement_field_fails_loudly_naming_it(
    tmp_path: Path, field: str, value: str
) -> None:
    """SC-8 (worker-confinement): a malformed value is an error that names the field."""
    with pytest.raises(ProjectConfigError, match=field):
        load_project_config(_write(tmp_path, f"[project]\n{field} = {value}\n"))


def test_sc8_an_invalid_config_is_unconstructible_directly() -> None:
    """SC-8 (worker-confinement): validated in the value, not only in the loader."""
    from agent_framework.project import ProjectConfig

    with pytest.raises(ProjectConfigError, match="session_network"):
        ProjectConfig(session_network=("https://pypi.org",))
    with pytest.raises(ProjectConfigError, match="session_write_paths"):
        ProjectConfig(session_write_paths=("relative/path",))


def test_protected_paths_and_test_paths_share_one_matcher() -> None:
    """The pattern semantics a project learns for `test_paths` hold for `protected_paths`."""
    from agent_framework.project import path_matches

    assert path_matches(".github/workflows/ci.yml", DEFAULTS.protected_paths)
    assert path_matches("agent-framework.toml", DEFAULTS.protected_paths)
    assert not path_matches("src/agent-framework.toml", DEFAULTS.protected_paths)
    assert not path_matches("docs/.github.md", DEFAULTS.protected_paths)
    assert path_matches("tests/deep/test_x.py", DEFAULTS.test_paths)
