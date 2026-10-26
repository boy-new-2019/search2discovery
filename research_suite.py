#!/usr/bin/env python3
"""Compatibility shim for historical integration tests and existing scripts.

Use the project-installed research-cognition-engine/scripts/suite.py for
new workflows. This shim intentionally avoids duplicating orchestration logic.
"""
from __future__ import annotations
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT_DIR = HERE / 'research-cognition-engine' / 'scripts'
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from suite import *  # noqa: F401,F403,E402 -- preserve old module-wide integration API

if __name__ == '__main__':
    raise SystemExit(main())
