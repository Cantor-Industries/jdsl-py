#!/usr/bin/env python3
"""jdsl Gemini CLI hook forwarder (design §29.2).

Reads Gemini's structured JSON hook payload from stdin, forwards it to the local
jdsl harness ingest daemon, emits valid (empty) hook output, and exits quickly.

Design constraints it honors:
- Uses only the structured JSON payload, never scraped terminal text (§8.2).
- Fails open: any error (daemon down, timeout, bad JSON) still exits 0 with empty
  output so the agent loop is never blocked or failed (§7.2). Observation must
  never take the agent down.
- Depends on nothing but the standard library, so it runs in the host's Python.

Config via environment:
    JDSL_INGEST_URL   default http://127.0.0.1:8848
    JDSL_CAPTURE_ID   default cap_gemini   (route events into a named capture)
    JDSL_HOOK_TIMEOUT default 0.5 seconds  (never wait long on the hot path)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # fail open

    base = os.environ.get("JDSL_INGEST_URL", "http://127.0.0.1:8848").rstrip("/")
    cap = os.environ.get("JDSL_CAPTURE_ID", "cap_gemini")
    timeout = float(os.environ.get("JDSL_HOOK_TIMEOUT", "0.5"))
    url = f"{base}/hook/gemini?cap={cap}"

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        pass  # daemon not running / slow — capture is best-effort (§7.2)

    # emit valid, non-blocking hook output
    print(json.dumps({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
