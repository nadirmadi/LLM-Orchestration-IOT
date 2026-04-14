"""
test_crew_real_badge.py — End-to-end crew test with a REAL, physical
patient badge instead of the Python fake ESP32s.

Prerequisites:
    - The badge firmware is flashed and running on the WiFi
    - You know the badge's IP (check the serial monitor for "IP : x.x.x.x")
    - The Docker stack is up:
        docker compose --profile dockered-ollama up -d --build
    - Ollama has qwen2.5:7b pulled

Usage (from the llmthings_v2 folder):
    # Inside the crew container (recommended):
    docker compose --profile dockered-ollama run --rm crew \\
        python -m scripts.test_crew_real_badge

    # Or with a custom badge IP:
    docker compose --profile dockered-ollama run --rm crew \\
        bash -c 'BADGE_IP=192.168.89.24 python -m scripts.test_crew_real_badge'

What this test does:
    1. Runs monitoring_discover_network against the real badge (as seed)
    2. Confirms the badge is stored in the DB with its canonical shape
    3. Runs crew.kickoff() with a nurse intent that only needs the badge
    4. Lets the LLMs reason about and report on the real device

The scenario is voluntarily narrower than test_crew_e2e.py: since we only
have one physical device right now (the badge), we ask a question the
agents can actually answer with that device alone — no corridor cameras
to activate yet.
"""

import os
import sys
import asyncio


# ─────────────────────────────────────────────────────────────────
# Where is the real badge?
#
# You can override this on the command line:
#   BADGE_IP=192.168.89.24 python -m scripts.test_crew_real_badge
#
# The default here matches the IP we've been using during development.
# Change it if your badge took a different address from DHCP.
# ─────────────────────────────────────────────────────────────────
BADGE_IP   = os.getenv("BADGE_IP", "192.168.89.24")
BADGE_PORT = os.getenv("BADGE_PORT", "80")
BADGE_ADDR = f"{BADGE_IP}:{BADGE_PORT}"

# Use a dedicated DB file so this test does not pollute the main one.
os.environ.setdefault("DB_PATH", "/data/llmthings_real_badge.db")


def section(title: str):
    print()
    print("═" * 70)
    print(title)
    print("═" * 70)


# ─────────────────────────────────────────────────────────────────
# 1. Pre-flight check — is the badge reachable at all?
# ─────────────────────────────────────────────────────────────────
section(f"Pre-flight: can we reach the badge at http://{BADGE_ADDR}/ ?")

import urllib.request
import urllib.error

try:
    with urllib.request.urlopen(
        f"http://{BADGE_ADDR}/capabilities", timeout=5
    ) as r:
        raw = r.read().decode()
        print(f"  OK — badge answered ({len(raw)} bytes)")
        print(f"  Preview: {raw[:200]}{'...' if len(raw) > 200 else ''}")
except urllib.error.URLError as e:
    print(f"  FAILED — cannot reach the badge: {e}")
    print()
    print("  Checks to run:")
    print(f"    - Is the badge powered on and connected to WiFi?")
    print(f"    - Is its IP really {BADGE_IP}? Check the Arduino serial monitor.")
    print(f"    - Is your Docker container on the same network as the badge?")
    print(f"      (If in doubt, try: docker compose exec crew ping {BADGE_IP})")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────
# 2. Reset and populate the DB via mesh discovery
# ─────────────────────────────────────────────────────────────────
section("Mesh discovery from the real badge as seed")

# Wipe any previous run so we start clean
db_path = os.environ["DB_PATH"]
if os.path.exists(db_path):
    os.remove(db_path)

from database import init_db  # noqa: E402
from mcp_server.tools.monitoring_tools import discover_network  # noqa: E402

init_db()

print(f"  Running discover_network(seed_ip={BADGE_ADDR!r})...")
disc = asyncio.run(discover_network(BADGE_ADDR))

if not disc["ok"]:
    print(f"  FAILED: {disc.get('error')}")
    sys.exit(1)

print(f"  OK — {disc['count']} device(s) discovered and stored in DB:")
for d in disc["discovered"]:
    services = [s["name"] for s in d["services"]]
    print(f"    {d['device_id']:<12} "
          f"zone={d['location']['zone']:<14} "
          f"services={services}")

if disc["failed"]:
    print(f"  Warning: {len(disc['failed'])} probe(s) failed:")
    for f in disc["failed"]:
        print(f"    - {f}")


# ─────────────────────────────────────────────────────────────────
# 3. Run the crew with a real-badge-friendly intent
# ─────────────────────────────────────────────────────────────────
section("Run crew.kickoff() with a nurse intent")

from crew.crew import build_crew_from_mcp  # noqa: E402

intent = "Which devices are currently on the patient, and what can they sense?"

print(f"  Intent: {intent!r}")
print()

# Point the crew at the in-process MCP that we are going to spawn below.
# We reuse the same trick as test_crew_e2e.py: start the MCP server in a
# subprocess so it has its own event loop and port.
import subprocess
import socket
import time
from pathlib import Path

MCP_PORT = "8770"
os.environ["MCP_PORT"] = MCP_PORT
os.environ["MCP_HOST"] = "0.0.0.0"
os.environ["MCP_SERVER_URL"] = f"http://127.0.0.1:{MCP_PORT}/mcp/"

repo_root = Path(__file__).resolve().parent.parent
mcp_proc = subprocess.Popen(
    [sys.executable, "-m", "mcp_server.server"],
    cwd=str(repo_root),
    env={**os.environ, "PYTHONPATH": str(repo_root)},
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

def port_open(host, port, timeout=0.3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

deadline = time.time() + 10
while time.time() < deadline:
    if port_open("127.0.0.1", int(MCP_PORT)):
        break
    time.sleep(0.2)
else:
    print("  MCP server failed to start.")
    if mcp_proc.stdout:
        print(mcp_proc.stdout.read())
    sys.exit(1)
print(f"  MCP server ready on 127.0.0.1:{MCP_PORT}")

try:
    with build_crew_from_mcp() as crew:
        result = crew.kickoff(inputs={"intent": intent})

    section("Final crew result")
    print(result)

finally:
    mcp_proc.terminate()
    try:
        mcp_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        mcp_proc.kill()
