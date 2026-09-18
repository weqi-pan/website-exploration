"""Bootstrap the skill into a self-contained, skill-local environment.

Nothing is installed into the global interpreter: everything (Python packages
and the Playwright browser) is placed under the skill directory, next to this
file. The skill therefore stays portable - copying the whole folder to another
machine and running this script is enough.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import skillenv


def main() -> None:
    python = skillenv.ensure_venv()
    env = skillenv.browser_env()

    subprocess.check_call(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(skillenv.REQUIREMENTS_FILE)],
        env=env,
    )
    subprocess.check_call(
        [str(python), "-m", "playwright", "install", "chromium"],
        env=env,
    )

    print("website-exploration runtime is ready")
    print(f"python:   {python}")
    print(f"venv:     {skillenv.VENV_DIR}")
    print(f"browsers: {skillenv.BROWSERS_DIR}")


if __name__ == "__main__":
    main()
