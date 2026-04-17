#!/usr/bin/env python3
"""
Build a standalone LabBench executable.

Usage:
    python scripts/build_app.py                  # onedir bundle (default)
    python scripts/build_app.py --onefile        # single-file executable
    python scripts/build_app.py --clean          # wipe build/ and dist/ first
    python scripts/build_app.py --tests          # run tests before building

Output:
    macOS:   dist/LabBench.app            (or dist/LabBench for onefile)
    Windows: dist/LabBench/LabBench.exe   (or dist/LabBench.exe for onefile)
    Linux:   dist/LabBench/LabBench       (or dist/LabBench for onefile)

Runs locally (developer machine) and in CI — same command, same spec,
same output layout.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = REPO_ROOT / "build" / "u2702a.spec"


def run(cmd: list[str], *, env: dict | None = None) -> None:
    """Run a subprocess, echo the command, abort on non-zero exit."""
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env or os.environ.copy())
    if result.returncode != 0:
        sys.exit(result.returncode)


def clean_build_dirs() -> None:
    for d in ("build/LabBench", "build/__pycache__", "dist"):
        path = REPO_ROOT / d
        if path.exists():
            print(f"rm -rf {path}")
            shutil.rmtree(path)


def run_tests() -> None:
    """Run the headless test suite. Fail the build if tests fail."""
    print(">>> Running test suite…")
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])


def pyinstaller_cmd(onefile: bool) -> list[str]:
    return [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--distpath", str(REPO_ROOT / "dist"),
        "--workpath", str(REPO_ROOT / "build"),
        str(SPEC_FILE),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--onefile", action="store_true",
        help="produce a single-file executable instead of an app bundle",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="wipe build/ and dist/ before building",
    )
    parser.add_argument(
        "--tests", action="store_true",
        help="run the test suite first; fail the build if any test fails",
    )
    args = parser.parse_args()

    if not SPEC_FILE.exists():
        print(f"ERROR: spec file not found at {SPEC_FILE}", file=sys.stderr)
        return 1

    if args.clean:
        clean_build_dirs()
    if args.tests:
        run_tests()

    env = os.environ.copy()
    env["REPO_ROOT"] = str(REPO_ROOT)
    env["ONEFILE"] = "1" if args.onefile else "0"

    run(pyinstaller_cmd(args.onefile), env=env)

    dist = REPO_ROOT / "dist"
    print()
    print(">>> Build complete. Artifacts:")
    for entry in sorted(dist.iterdir()):
        print(f"    {entry}")
    print()
    print("Run it:")
    if sys.platform == "darwin" and not args.onefile:
        print(f"  open {dist / 'LabBench.app'}")
    elif sys.platform == "win32":
        print(f"  {dist / ('LabBench.exe' if args.onefile else 'LabBench' / 'LabBench.exe')}")
    else:
        print(f"  {dist / ('LabBench' if args.onefile else 'LabBench' / 'LabBench')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
