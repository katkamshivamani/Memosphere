"""Shared pytest configuration.

Qt runs offscreen so UI tests work in CI and on machines without a display.
Live provider tests are opt-in via environment variables.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
