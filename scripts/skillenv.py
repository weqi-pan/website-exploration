"""Skill-local environment helpers.

This module is intentionally limited to the standard library so it can be
imported by the global interpreter before the skill's own virtual environment
exists. It locates the skill relative to this file, so the skill stays
portable (copy the whole directory anywhere and it still resolves its own
``.venv`` and browser cache).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
VENV_DIR = SKILL_ROOT / ".venv"
REQUIREMENTS_FILE = SCRIPTS_DIR / "requirements.txt"
BROWSERS_DIR = SKILL_ROOT / ".playwright-browsers"

REEXEC_FLAG = "WEBSITE_EXPLORATION_VENV"


def venv_python() -> Path:
    """Path to the python executable inside the skill-local virtual env."""
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_ready() -> bool:
    return venv_python().exists()


def using_skill_venv() -> bool:
    """True when the current interpreter *is* the skill-local venv."""
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def ensure_venv() -> Path:
    """Create the skill-local virtual environment if it does not exist yet."""
    python = venv_python()
    if python.exists():
        return python
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
    if not python.exists():
        raise RuntimeError(f"创建内置虚拟环境失败: {VENV_DIR}")
    return python


def browser_env() -> dict[str, str]:
    """Environment for child processes: local venv marker + local browsers."""
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_DIR)
    env[REEXEC_FLAG] = "1"
    return env


def reexec_in_venv(argv: list[str] | None = None) -> bool:
    """Replace the current process with the skill venv interpreter.

    Returns ``True`` if the process was replaced (the caller should stop).
    Returns ``False`` when no re-exec is needed or the venv is unavailable.
    """
    if using_skill_venv() or os.environ.get(REEXEC_FLAG) == "1":
        return False
    python = venv_python()
    if not python.exists():
        return False
    args = list(argv) if argv is not None else sys.argv
    os.execve(str(python), [str(python), *args], browser_env())
    return True  # pragma: no cover - execve never returns
