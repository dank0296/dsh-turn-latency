#!/usr/bin/env python3
"""Print a dsh session timeline and flag inter-event gaps over 1 s.

Usage: python3 session-timeline.py <session.v4.jsonl.zstd>

Handles both plain .jsonl and zstd-compressed session files.
"""
import json
import subprocess
import sys


def read(path: str) -> bytes:
    if path.endswith(".zst") or path.endswith(".zstd"):
        return subprocess.run(["zstdcat", path], capture_output=True).stdout
    with open(path, "rb") as fh:
        return fh.read()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    events = []
    for line in read(sys.argv[1]).decode(errors="replace").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        events.append((d.get("time") or 0, d.get("type") or "?", d.get("data") or {}))
    if not events:
        print("no events")
        return 1
    t0 = events[0][0]
    prev = t0
    for ts, typ, data in events:
        gap = (ts - prev) / 1000.0
        prev = ts
        rel = (ts - t0) / 1000.0
        if typ in ("turn/start", "turn/end", "step/start", "step/end",
                   "assistant/message", "session/title", "user/message"):
            extra = ""
            if typ == "assistant/message":
                content = (data.get("message") or {}).get("content")
                extra = " " + str(content)[:40]
            print(f"+{rel:7.2f}s  (+{gap:6.2f})  {typ}{extra}")
        elif gap > 1.0:
            print(f"+{rel:7.2f}s  (+{gap:6.2f})  [gap] {typ}")
    print(f"total: {(events[-1][0] - t0) / 1000.0:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
