"""Console entry points for the worker and validator CLIs.

Verifies spec success criteria:
- SC-4: the installed console commands invoke the same `main` functions as
  the `python -m` forms — checked at the packaging metadata level (the
  entry point's declared target) and behaviorally (the loaded callable is
  the same object, and reacts to `--help` the way `python -m` does).
"""

from __future__ import annotations

import importlib.metadata

import pytest

from agent_framework.validator.__main__ import main as validator_main
from agent_framework.worker.__main__ import main as worker_main

_EXPECTED = {
    "agent-framework-worker": "agent_framework.worker.__main__:main",
    "agent-framework-validate": "agent_framework.validator.__main__:main",
}


def _entry_points() -> dict[str, importlib.metadata.EntryPoint]:
    eps = importlib.metadata.entry_points(group="console_scripts")
    return {ep.name: ep for ep in eps if ep.name in _EXPECTED}


def test_sc4_entry_points_declared_in_packaging_metadata() -> None:
    """SC-4: both console commands are registered and map to the documented targets."""
    found = _entry_points()
    assert set(found) == set(_EXPECTED)
    assert {name: ep.value for name, ep in found.items()} == _EXPECTED


def test_sc4_worker_entry_point_loads_the_same_main_as_python_dash_m() -> None:
    """SC-4: `agent-framework-worker` loads worker.__main__.main itself, not a copy."""
    loaded = _entry_points()["agent-framework-worker"].load()
    assert loaded is worker_main


def test_sc4_validate_entry_point_loads_the_same_main_as_python_dash_m() -> None:
    """SC-4: `agent-framework-validate` loads validator.__main__.main itself, not a copy."""
    loaded = _entry_points()["agent-framework-validate"].load()
    assert loaded is validator_main


def test_sc4_worker_entry_point_help_behaves_like_python_dash_m(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SC-4: the entry-point callable exits 0 on --help, same as `python -m` argparse."""
    loaded = _entry_points()["agent-framework-worker"].load()
    with pytest.raises(SystemExit) as exc_info:
        loaded(["--help"])
    assert exc_info.value.code == 0
    capsys.readouterr()


def test_sc4_validate_entry_point_help_behaves_like_python_dash_m(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SC-4: the entry-point callable exits 0 on --help, same as `python -m` argparse."""
    loaded = _entry_points()["agent-framework-validate"].load()
    with pytest.raises(SystemExit) as exc_info:
        loaded(["--help"])
    assert exc_info.value.code == 0
    capsys.readouterr()
