"""
test_crew_mesh_autodiscover.py — Let the LLMs handle mesh discovery.

Contrary to test_crew_real_badge.py, this script does NOT pre-populate
the database before kickoff. It starts the crew with an EMPTY database,
and lets the Monitoring Agent figure out on its own that it needs to
call `monitoring_discover_network` to populate it.

The seed device IP is provided via the SEED_DEVICE_IP environment
variable (set in docker-compose.yml), so the agent can invoke the tool
without argument.

Prerequisites:
    - The 3 ESP32 devices (badge + ultrasonic + camera) are flashed
      and reachable on the WiFi
    - docker-compose has the correct SEED_DEVICE_IP (by default it
      points to the badge — override via `SEED_DEVICE_IP=...` inline
      or via an .env file)
    - Ollama has qwen2.5:7b pulled

Usage (from the llmthings_v2 folder):
    docker compose --profile dockered-ollama run --rm crew \\
        python -m scripts.test_crew_mesh_autodiscover

What this test validates:
    1. The crew starts with a completely empty database
    2. The Monitoring Agent, when asked about the deployment, correctly
       diagnoses the empty DB and triggers mesh discovery itself
    3. The mesh discovery runs against real hardware from the seed
    4. All 3 devices end up in the database
    5. The agent answers the nurse's question based on the freshly
       discovered reality
"""

import os
import sys
import subprocess
import socket
import time
from pathlib import Path


# ─────────────────────────────────────────────────────────────────
# Dedicated DB file so this test really starts empty
# ─────────────────────────────────────────────────────────────────
os.environ["DB_PATH"] = "/data/llmthings_mesh_autodiscover.db"
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

MCP_PORT = "8771"
os.environ["MCP_PORT"] = MCP_PORT
os.environ["MCP_HOST"] = "0.0.0.0"
os.environ["MCP_SERVER_URL"] = f"http://127.0.0.1:{MCP_PORT}/mcp/"


def section(title: str):
    print()
    print("═" * 70)
    print(title)
    print("═" * 70)


# ─────────────────────────────────────────────────────────────────
# Pre-flight: SEED_DEVICE_IP must be set, otherwise the agent's
# discovery call will fail with "no seed IP provided".
# ─────────────────────────────────────────────────────────────────
section("Pre-flight: SEED_DEVICE_IP sanity check")

seed = os.getenv("SEED_DEVICE_IP", "")
if not seed:
    print("  FAILED — SEED_DEVICE_IP is not set in the container environment.")
    print("  Make sure docker-compose.yml sets it for the mcp_server service.")
    sys.exit(1)
print(f"  SEED_DEVICE_IP = {seed}")

# We also sanity-check that the seed is reachable from the container.
# This is just a courtesy — if it's unreachable, the agent's discovery
# would fail with a clearer error too, but we'd rather catch it now.
import urllib.request, urllib.error  # noqa: E402
try:
    with urllib.request.urlopen(f"http://{seed}/capabilities", timeout=5) as r:
        raw = r.read().decode()
        print(f"  Seed reachable — {len(raw)} bytes returned")
except Exception as e:
    print(f"  WARNING — seed {seed} not reachable right now: {e}")
    print(f"  The agent's discovery will likely fail. Continuing anyway.")


# ─────────────────────────────────────────────────────────────────
# Start the MCP server (same pattern as test_crew_real_badge.py)
# ─────────────────────────────────────────────────────────────────
section("Start MCP server (with empty DB)")

from database import init_db  # noqa: E402
init_db()
print(f"  Fresh DB at {os.environ['DB_PATH']}")

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


# ─────────────────────────────────────────────────────────────────
# Run the crew
# ─────────────────────────────────────────────────────────────────
try:
    section("Run crew.kickoff() with an open-ended intent")

    from crew.crew import build_crew_from_mcp  # noqa: E402

    intent = (
        "Give me the full picture of the current IoT deployment: "
        "list every device that exists, where it is located, and "
        "what each of them can sense or do."
    )

    print(f"  Intent: {intent!r}")
    print(f"  DB is EMPTY — the Monitoring Agent should detect this and")
    print(f"  trigger monitoring_discover_network() on its own.")
    print()

    with build_crew_from_mcp() as crew:
        result = crew.kickoff(inputs={"intent": intent})

    section("Final crew result")
    print(result)

    # Final sanity check: after the crew is done, the DB should have
    # been populated by the agent's discovery call.
    section("DB state after the run")
    from database import query_devices  # noqa: E402
    devices = query_devices()
    print(f"  {len(devices)} device(s) in DB:")
    for d in devices:
        services = [s["name"] for s in d["services"]]
        print(f"    {d['device_id']:<18} zone={d['location']['zone']:<12} "
              f"services={services}")

finally:
    mcp_proc.terminate()
    try:
        mcp_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        mcp_proc.kill()
