#!/usr/bin/env python3
"""Create or reuse the Skill-local Python environment and report its interpreter.

Every later script runs against one pinned interpreter instead of whatever
``python3`` happens to resolve to on the machine. The last line is always
``ENV_PY=<path>``; capture it and use that interpreter for the rest of the run.

    python3 scripts/prepare_env.py          # create or repair, then print ENV_PY
    python3 scripts/prepare_env.py --check  # probe only; exit 1 when incomplete
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
VENV_ROOT = SKILL_ROOT / ".venv"
REQUIREMENTS = SKILL_ROOT / "requirements.txt"
MINIMUM_PYTHON = (3, 8)
# Import name -> requirement line prefix in requirements.txt.
IMPORT_NAMES = {"requests": "requests", "urllib3": "urllib3"}


def interpreter_path() -> Path:
    if sys.platform.startswith("win"):
        return VENV_ROOT / "Scripts" / "python.exe"
    return VENV_ROOT / "bin" / "python"


def interpreter_version(python: Path) -> tuple[int, int] | None:
    probe = subprocess.run(
        [str(python), "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return None
    try:
        major, minor = probe.stdout.split()
        return int(major), int(minor)
    except ValueError:
        return None


def missing_imports(python: Path) -> list[str]:
    missing = []
    for import_name in sorted(IMPORT_NAMES):
        probe = subprocess.run(
            [str(python), "-c", f"import {import_name}"], capture_output=True
        )
        if probe.returncode != 0:
            missing.append(import_name)
    return missing


def install_requirements(python: Path) -> bool:
    if not REQUIREMENTS.is_file():
        print(f"[err] missing {REQUIREMENTS.name}", file=sys.stderr)
        return False
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[err] pip install failed: {result.stderr.strip()[-800:]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="probe only; never create or install"
    )
    args = parser.parse_args()

    if sys.version_info[:2] < MINIMUM_PYTHON and not VENV_ROOT.exists():
        print(
            f"[err] this interpreter is {sys.version_info[0]}.{sys.version_info[1]}; "
            f"run prepare_env.py with Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer",
            file=sys.stderr,
        )
        return 1

    python = interpreter_path()
    if not python.exists():
        if args.check:
            print(f"[err] no Skill environment at {VENV_ROOT}", file=sys.stderr)
            return 1
        venv.create(str(VENV_ROOT), with_pip=True)

    version = interpreter_version(python)
    if version is None:
        print(f"[err] {python} is not runnable; delete {VENV_ROOT} and retry", file=sys.stderr)
        return 1
    if version < MINIMUM_PYTHON:
        print(
            f"[err] {python} is {version[0]}.{version[1]}; "
            f"Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer is required",
            file=sys.stderr,
        )
        return 1

    missing = missing_imports(python)
    if missing:
        if args.check:
            print("[err] missing packages: " + ", ".join(missing), file=sys.stderr)
            return 1
        if not install_requirements(python):
            return 1
        missing = missing_imports(python)
        if missing:
            print("[err] still missing after install: " + ", ".join(missing), file=sys.stderr)
            return 1

    print(f"[ok] python {version[0]}.{version[1]}, pinned requirements present")
    print(f"ENV_PY={python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
