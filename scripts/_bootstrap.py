"""Make ``binomial_arbitrage`` importable when the package is not installed.

The scripts work after ``pip install -e .``; this fallback only adds the
project's ``src`` directory (resolved relative to this file, never a
hard-coded path) if the import would otherwise fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    import binomial_arbitrage  # noqa: F401
except ImportError:  # pragma: no cover - only used without installation
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
