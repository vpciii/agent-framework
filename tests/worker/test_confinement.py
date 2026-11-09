"""The confinement profile (specs/worker-confinement, ADR 0007).

Verifies:
- SC-1: every launch carries the whole profile.
- SC-2: the sandbox settings rendered from project config — nothing widened
  unless declared; exactly the declarations added.
- SC-3: no caller can pass arguments through to the session.
- SC-4: the session's environment is an allowlist.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_framework.project import ProjectConfig
from agent_framework.worker.__main__ import main
from agent_framework.worker.confinement import profile_args, sandbox_settings, session_env
from agent_framework.worker.orchestrator import work

from .test_orchestrator import _GitGh, _roster, repo  # noqa: F401

_ROOTS = ("/work/repo", "/work/repo/.git")


def _launch(
    repo: Path, project: ProjectConfig, environ: Mapping[str, str]  # noqa: F811
) -> tuple[list[str], dict[str, str]]:
    """Dispatch one task through `work()` with a fake session; return what
    the session seam was handed."""
    seen: list[tuple[list[str], dict[str, str]]] = []

    def session(args: Sequence[str], cwd: Path, timeout_s: float, env: Mapping[str, str]) -> None:
        seen.append((list(args), dict(env)))
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / ".worker-result.json").write_text(
            json.dumps({"status": "completed", "detail": "done"}), encoding="utf-8"
        )

    work("fixture", "T-1", _roster(), specs_dir=repo / "specs", project=project,
         run=_GitGh(), session_run=session, environ=environ)
    [(args, env)] = seen
    return args, env


def _settings(args: list[str]) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(args[args.index("--settings") + 1])
    return loaded


def test_sc1_every_launch_carries_the_whole_profile(repo: Path) -> None:  # noqa: F811
    """SC-1: restricted, fixed tools, nothing prompts, no outside settings or
    MCP servers, and a sandbox that is on, cannot be opted out of, and fails closed."""
    args, _ = _launch(repo, ProjectConfig(), {"PATH": "/usr/bin"})

    assert args[:2] == ["claude", "-p"] and "--restricted" in args
    assert args[args.index("--tools") + 1] == "Bash,Read,Edit,Write,Glob,Grep"
    assert args[args.index("--permission-mode") + 1] == "acceptEdits"
    assert args[args.index("--permission-prompts") + 1] == "none"
    assert "--strict-mcp-config" in args
    assert not any("dangerously" in a or a == "bypassPermissions" for a in args)

    sandbox = _settings(args)["sandbox"]
    assert sandbox["enabled"] is True
    assert sandbox["failIfUnavailable"] is True
    assert sandbox["allowUnsandboxedCommands"] is False
    assert "excludedCommands" not in sandbox  # no command is exempted


def test_sc2_nothing_is_widened_unless_the_project_declares_it() -> None:
    """SC-2: no extra writable path, home unreadable but for the repository
    and git's user configuration, no reachable host, strict refusal."""
    sandbox = sandbox_settings(ProjectConfig(), _ROOTS)["sandbox"]

    assert sandbox["filesystem"]["allowWrite"] == []
    assert sandbox["filesystem"]["denyRead"] == ["~/"]
    assert sandbox["filesystem"]["allowRead"] == [
        "/work/repo", "/work/repo/.git", "~/.gitconfig", "~/.config/git",
    ]
    assert sandbox["network"] == {"allowedDomains": [], "strictAllowlist": True}


def test_sc2_exactly_the_declared_paths_and_hosts_are_added() -> None:
    """SC-2: declarations widen the profile by themselves and nothing else."""
    project = ProjectConfig(
        session_write_paths=("~/.cache/uv",),
        session_read_paths=("~/.local/share/uv",),
        session_network=("pypi.org", "files.pythonhosted.org"),
    )
    sandbox = sandbox_settings(project, _ROOTS)["sandbox"]

    assert sandbox["filesystem"]["allowWrite"] == ["~/.cache/uv"]
    assert sandbox["filesystem"]["allowRead"] == [
        "/work/repo", "/work/repo/.git", "~/.gitconfig", "~/.config/git",
        "~/.local/share/uv", "~/.cache/uv",  # a writable path is readable too
    ]
    assert sandbox["network"]["allowedDomains"] == ["pypi.org", "files.pythonhosted.org"]
    assert sandbox["network"]["strictAllowlist"] is True


def test_sc3_no_caller_can_pass_arguments_to_the_session(
    repo: Path, capsys: pytest.CaptureFixture[str]  # noqa: F811
) -> None:
    """SC-3: the CLI rejects --session-arg; `work()` has no such parameter;
    the launch is the brief, the model and the profile — nothing else."""
    with pytest.raises(SystemExit) as exit_info:
        main(["fixture", "T-1", "--session-arg=--dangerously-skip-permissions"])
    assert exit_info.value.code == 2
    assert "session-arg" in capsys.readouterr().err

    assert "session_args" not in inspect.signature(work).parameters

    args, _ = _launch(repo, ProjectConfig(), {"PATH": "/usr/bin"})
    brief = args[2]
    profile = list(profile_args(ProjectConfig(), (str(repo.resolve()),)))
    assert args == ["claude", "-p", brief, "--model", "worker-model-x", *profile]


def test_sc4_the_session_environment_is_an_allowlist(repo: Path) -> None:  # noqa: F811
    """SC-4: secret-looking variables do not reach the session; the fixed
    base and declared names do."""
    environ = {
        "PATH": "/usr/bin", "HOME": "/Users/x", "LANG": "en_US.UTF-8", "LC_ALL": "C",
        "TMPDIR": "/tmp/x", "ANTHROPIC_API_KEY": "session-tool-auth",
        "CLAUDE_CONFIG_DIR": "/Users/x/.claude",
        # A dispatching Claude Code session's own variables: identifying, and
        # its configuration — not the worker's.
        "CLAUDE_CODE_USER_EMAIL": "x@example.com", "CLAUDE_CODE_ACCOUNT_UUID": "acct",
        "CLAUDE_CODE_SESSION_ID": "host-session", "CLAUDE_CODE_SIMPLE": "1",
        "GH_TOKEN": "s3cret", "GEMINI_API_KEY": "s3cret", "AF_HA_WEBHOOK_URL": "https://ha/hook",
        "AWS_SECRET_ACCESS_KEY": "s3cret", "UV_INDEX_URL": "https://index", "EDITOR": "vi",
    }
    _, env = _launch(repo, ProjectConfig(session_env=("UV_INDEX_URL",)), environ)

    assert env == {
        "PATH": "/usr/bin", "HOME": "/Users/x", "LANG": "en_US.UTF-8", "LC_ALL": "C",
        "TMPDIR": "/tmp/x", "ANTHROPIC_API_KEY": "session-tool-auth",
        "CLAUDE_CONFIG_DIR": "/Users/x/.claude", "UV_INDEX_URL": "https://index",
    }
    assert "s3cret" not in env.values()
    assert not any(name.startswith("CLAUDE_CODE_") for name in env)
    # The session tool's own backend selection and headless credential do pass.
    kept = session_env(ProjectConfig(), {
        "CLAUDE_CODE_OAUTH_TOKEN": "t", "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_CODE_USE_VERTEX": "1", "CLAUDE_CODE_ANYTHING_ELSE": "x",
    })
    assert sorted(kept) == [
        "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
    ]
    assert session_env(ProjectConfig(), environ).get("UV_INDEX_URL") is None  # undeclared


def test_the_default_seam_hands_the_process_only_the_given_environment(tmp_path: Path) -> None:
    """The real subprocess seam: the child sees the allowlisted environment,
    not this process's, and its standard input is closed."""
    import os
    import sys

    from agent_framework.worker.session import run_claude

    os.environ["AF_TEST_LEAK"] = "leaked"
    try:
        out = tmp_path / "seen.json"
        script = (
            "import json, os, sys\n"
            f"json.dump({{'env': dict(os.environ), 'stdin': sys.stdin.read()}}, open({str(out)!r}, 'w'))\n"
        )
        run_claude([sys.executable, "-c", script], tmp_path, 20, {"ONLY": "this"})
    finally:
        del os.environ["AF_TEST_LEAK"]

    seen = json.loads(out.read_text())
    assert seen["env"].get("ONLY") == "this"
    assert "AF_TEST_LEAK" not in seen["env"]
    assert seen["stdin"] == ""
