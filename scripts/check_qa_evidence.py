#!/usr/bin/env python3
"""Ensure committed pet QA reports attest the current approved atlas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "bubbles/spritesheet.png"
REPORTS = [ROOT / "docs/validation.json", ROOT / "docs/quality-gate.json"]


def main() -> None:
    expected_sha = hashlib.sha256(ATLAS.read_bytes()).hexdigest()
    for path in REPORTS:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("ok") is not True:
            raise SystemExit(f"{path.relative_to(ROOT)} is not a passing report")
        if report.get("sha256") != expected_sha:
            raise SystemExit(f"{path.relative_to(ROOT)} does not attest the current atlas")
        report_path = report.get("file", report.get("atlas"))
        if report_path != "bubbles/spritesheet.png":
            raise SystemExit(f"{path.relative_to(ROOT)} contains a stale or non-portable atlas path")
    print(f"QA evidence matches bubbles/spritesheet.png ({expected_sha})")


if __name__ == "__main__":
    main()
