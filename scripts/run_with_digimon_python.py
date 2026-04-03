#!/usr/bin/env python3
"""Exec a command under the resolved DIGIMON runtime interpreter."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.runtime_paths import resolve_digimon_python


def _help_text() -> str:
    """Render a compact wrapper help message without stealing child `--help` flags."""
    return (
        "usage: run_with_digimon_python.py [--print-path] <python-args...>\n\n"
        "Resolve the DIGIMON runtime interpreter, then exec the requested Python command.\n"
        "Examples:\n"
        "  python scripts/run_with_digimon_python.py --print-path\n"
        "  python scripts/run_with_digimon_python.py eval/run_agent_benchmark.py --help\n"
        "  python scripts/run_with_digimon_python.py -m llm_client recent --project Digimon_for_KG_application\n"
    )


def main() -> int:
    """Resolve the DIGIMON interpreter, then exec the requested command."""
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit("No command provided. Example: scripts/run_with_digimon_python.py -m llm_client")
    if argv == ["-h"] or argv == ["--help"]:
        print(_help_text(), end="")
        return 0

    python_path = resolve_digimon_python()
    if argv == ["--print-path"]:
        print(python_path)
        return 0

    env = os.environ.copy()
    env.setdefault("DIGIMON_PYTHON", str(python_path))
    os.execvpe(str(python_path), [str(python_path), *argv], env)


if __name__ == "__main__":
    raise SystemExit(main())
