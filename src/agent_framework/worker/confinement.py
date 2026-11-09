"""The confinement profile: the limits every worker session is launched under.

ADR 0007: the framework owns the session's permissions. A session gets a
fixed tool list, never prompts, loads none of the user's or project's Claude
settings, and runs every command in an OS sandbox that fails closed. By
default a command writes only in its worktree, reaches no network host, and
reads nothing under the home directory but the repository and git's user
configuration; a project widens that only by declaring paths, hosts and
variable names in `agent-framework.toml`. No caller can widen it at dispatch.

Pure: every limit here is a value computed from `ProjectConfig`, so a test
asserts it by reading it. This module is Claude Code's mechanism and sits
behind the session seam (ADR 0001, ADR 0004) — another session tool would
bring its own profile.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..project import ProjectConfig

# What a session needs to read, edit and run commands in its worktree.
TOOLS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep")

# The environment a session and ordinary commands need; everything else in
# the dispatching environment is dropped unless the project names it.
_BASE_ENV = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TERM", "TMPDIR")
# Locale settings, and the session tool's authentication and endpoint.
_ENV_PREFIXES = ("LC_", "ANTHROPIC_")
# Where the session tool finds its configuration and which backend it
# authenticates to — named one by one. Not the CLAUDE_ prefix: a dispatching
# Claude Code session exports dozens of its own variables under it (the
# account's email and ids, its session id, its settings), none of which is
# the worker's to read (plan, "The environment, exactly").
_SESSION_TOOL_ENV = (
    "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
)

# Readable under the otherwise-denied home directory: git needs the user's
# identity to commit.
_GIT_USER_CONFIG = ("~/.gitconfig", "~/.config/git")


def session_env(project: ProjectConfig, environ: Mapping[str, str]) -> dict[str, str]:
    """The session's process environment: an allowlist of `environ`."""
    allowed = {*_BASE_ENV, *_SESSION_TOOL_ENV, *project.session_env}
    return {
        name: value
        for name, value in environ.items()
        if name in allowed or name.startswith(_ENV_PREFIXES)
    }


def sandbox_settings(project: ProjectConfig, read_roots: tuple[str, ...]) -> dict[str, Any]:
    """The sandbox every command of the session runs in.

    `read_roots` are the repository's own directories (its root and, when it
    lies elsewhere, its git directory) — the only paths under the home
    directory a command may read without the project declaring them.
    """
    return {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,  # no sandbox, no session
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,  # a command cannot opt out
            "network": {
                "allowedDomains": list(project.session_network),
                "strictAllowlist": True,  # refuse an undeclared host; never prompt
            },
            "filesystem": {
                "denyRead": ["~/"],
                "allowRead": [
                    *read_roots,
                    *_GIT_USER_CONFIG,
                    *project.session_read_paths,
                    *project.session_write_paths,
                ],
                "allowWrite": list(project.session_write_paths),
            },
        }
    }


def profile_args(project: ProjectConfig, read_roots: tuple[str, ...]) -> tuple[str, ...]:
    """The session CLI's arguments that carry the profile.

    The settings ride inline, not as a file: nothing in the worktree for a
    session to edit.
    """
    return (
        "--restricted",
        "--tools", ",".join(TOOLS),
        "--permission-mode", "acceptEdits",  # edits inside the working directory only
        "--permission-prompts", "none",  # whatever else would prompt is denied
        "--strict-mcp-config",
        "--settings", json.dumps(sandbox_settings(project, read_roots)),
    )
