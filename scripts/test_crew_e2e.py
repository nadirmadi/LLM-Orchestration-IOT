"""
test_crew_e2e.py — Full end-to-end test with the LLMs.

REQUIRES:
    - Ollama running locally (default: http://localhost:11434)
    - The model `llama3.1` (or `llama3.1:8b`) pulled:
        ollama pull llama3.1
    - The other deps installed:
        pip install -r mcp_server/requirements.txt
        pip install -r crew/requirements.txt
        pip install fastapi uvicorn

This test boots:
    - 4 fake ESP32s in background threads
    - The MCP server in a subprocess
    - Then runs `crew.kickoff()` with a nurse intent

You should see (in verbose mode):
    - The Orchestration Agent reasoning about the intent
    - It delegating to the Monitoring Agent in natural language
    - The Monitoring Agent calling monitoring_discover_network and
      monitoring_read_devices via the MCP tools
    - The Monitoring Agent answering the Orchestration Agent in JSON
    - The Orchestration Agent calling orchestration_wake_up_device
      and orchestration_activate_service
    - A final summary report

Usage:
    # Make sure Ollama is running first:
    ollama serve &
    ollama pull llama3.1

    python -m scripts.test_crew_e2e
"""

import os
import sys
import time
import asyncio
import tempfile
import subprocess
import threading
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
# Fresh DB and dedicated MCP port
# ─────────────────────────────────────────────────────────────────
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "llmthings_e2e_crew.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

MCP_PORT = "8767"
os.environ["MCP_PORT"] = MCP_PORT
os.environ["MCP_HOST"] = "127.0.0.1"
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("MONITORING_MODEL",    "ollama/llama3.1")
os.environ.setdefault("ORCHESTRATION_MODEL", "ollama/llama3.1")

# Tell the crew module which MCP URL to use
os.environ["MCP_SERVER_URL"] = f"http://127.0.0.1:{MCP_PORT}/mcp/"


def section(title: str):
    print()
    print("═" * 70)
    print(title)
    print("═" * 70)


# ─────────────────────────────────────────────────────────────────
# 1. Boot fake ESP32s
# ─────────────────────────────────────────────────────────────────
section("Boot 4 fake ESP32s")

import uvicorn
from scripts.fake_esp32 import DEPLOYMENT, make_app


def _run_fake(device):
    host, port = device["ip"].split(":")
    config = uvicorn.Config(
        make_app(device), host=host, port=int(port), log_level="error"
    )
    asyncio.run(uvicorn.Server(config).serve())


for d in DEPLOYMENT:
    threading.Thread(target=_run_fake, args=(d,), daemon=True).start()
print(f"  {len(DEPLOYMENT)} fake ESP32 threads started")
time.sleep(1.5)


# ─────────────────────────────────────────────────────────────────
# 2. Boot MCP server in subprocess
# ─────────────────────────────────────────────────────────────────
section("Boot MCP server")

repo_root = Path(__file__).resolve().parent.parent
mcp_proc = subprocess.Popen(
    [sys.executable, "-m", "mcp_server.server"],
    cwd=str(repo_root),
    env={**os.environ, "PYTHONPATH": str(repo_root)},
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

import socket
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
    print("  MCP server failed to start. Output:")
    if mcp_proc.stdout:
        print(mcp_proc.stdout.read())
    sys.exit(1)
print(f"  MCP server ready on 127.0.0.1:{MCP_PORT}")


# ─────────────────────────────────────────────────────────────────
# 3. Pre-populate the database with a mesh discovery
# ─────────────────────────────────────────────────────────────────
# We run discover_network ONCE before the crew starts. This way the
# Monitoring Agent can answer questions immediately from the DB without
# having to figure out the seed IP on its own (which it cannot do —
# SEED_DEVICE_IP is not set in this test, by design).
#
# In production, this would be either:
#   - done automatically at crew startup (e.g. a pre-task hook)
#   - done by the Monitoring Agent itself if it is given a seed IP
#
# Here we pre-populate to keep the scenario focused on the agent
# dialogue and tool calling, not on discovery plumbing.
section("Pre-populate DB via mesh discovery")

import asyncio as _asyncio
from mcp_server.tools.monitoring_tools import discover_network

seed_ip = "127.0.0.1:9001"
print(f"  Running discover_network(seed_ip={seed_ip!r})...")
disc_result = _asyncio.run(discover_network(seed_ip))
if not disc_result["ok"]:
    print(f"  FAILED: {disc_result.get('error')}")
    sys.exit(1)
print(f"  OK — {disc_result['count']} devices discovered and stored in DB")
for d in disc_result["discovered"]:
    services = [s["name"] for s in d["services"]]
    print(f"    {d['device_id']:<10} zone={d['location']['zone']:<14} "
          f"services={services}")


# ─────────────────────────────────────────────────────────────────
# 4. Build the crew and kickoff
# ─────────────────────────────────────────────────────────────────
try:
    section("Run crew.kickoff() with the nurse intent")

    from crew.crew import build_crew_from_mcp

    intent = (
        "Which devices are available in the corridor and can stream "
        "video? Wake them up and start their camera service so we can "
        "monitor the patient when she enters the corridor."
    )

    print(f"  Intent: {intent!r}")
    print()

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
