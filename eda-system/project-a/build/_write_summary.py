#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: _write_summary.py <gate> <status> <message>", file=sys.stderr)
        return 2

    gate = sys.argv[1]
    status = sys.argv[2]
    message = sys.argv[3]

    reports_dir = Path("reports") / gate
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "gate": gate,
        "status": status,
        "message": message,
        "returncode": 0 if status == "passed" else 1 if status == "failed" else 0,
        "generated_at": now_iso(),
        "artifacts": [],
    }
    (reports_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    aggregate = Path("reports") / "summary.json"
    aggregate.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
