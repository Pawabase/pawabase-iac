"""Run one flow now and print a compact trace: python scripts/trace.py <flow> '<json input>'"""

import json
import sys
from pathlib import Path

import httpx

root = Path(__file__).resolve().parent.parent
keys = {}
for name in (".env", ".env.local"):
    path = root / name
    if path.is_file():
        keys.update(dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#")))
flow, payload = sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
response = httpx.post(f"http://localhost:8080/platform/v1/envs/school/flows/{flow}/run", headers={"apikey": keys["SCHOOL_ADMIN_KEY"]}, json={"input": payload}, timeout=60)
body = response.json()
print("status:", body.get("status"), body.get("error", ""), body.get("code", ""), body.get("node", ""))
for step in body.get("trace", []):
    note = step["error"] or ""
    print(f"  {step['sequence']:>3} {step['node']:<22} {step['block']:<20} -> {step['handle'] or '-':<8} {step['status']:<9} {note[:150]}")
for log in body.get("logs", []):
    print("  log:", log)
