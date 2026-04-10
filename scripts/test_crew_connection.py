"""
test_crew_connection.py — Validate the wiring without requiring Ollama.

This test does NOT actually run the LLMs (you would need Ollama with
llama3.1 pulled for that). What it DOES validate is:

  1. The fake ESP32 deployment is reachable (4 devices on ports 9001..4)
  2. The MCP server starts and exposes the 9 tools
  3. CrewAI's MCPServerAdapter can connect over streamable-http
  4. The tools split correctly by prefix:
       - 5 monitoring_* tools
       - 4 orchestration_* tools
  5. We can build the two agents and the crew object
  6. We can invoke a tool through the CrewAI wrapper without errors
     (this proves the streamable-http session is healthy)

To run the actual end-to-end scenario with the LLMs, see
scripts/test_crew_e2e.py and make sure Ollama is running.

Usage:
    python -m scripts.test_crew_connection
"""

import os
import sys
import time
import json
import asyncio
import tempfile
import subprocess
import threading
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
# Make sure we use a fresh DB for this test
# ─────────────────────────────────────────────────────────────────
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "llmthings_crew_test.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

# Pick a non-default MCP port to avoid clashing with anything else
MCP_PORT = "8766"
os.environ["MCP_PORT"] = MCP_PORT
os.environ["MCP_HOST"] = "127.0.0.1"


def section(title: str):
    print()
    print("─" * 70)
    print(title)
    print("─" * 70)


# ─────────────────────────────────────────────────────────────────
# Boot the 4 fake ESP32s in background threads (in-process)
# ─────────────────────────────────────────────────────────────────
section("0. Boot 4 fake ESP32s")

import uvicorn
from scripts.fake_esp32 import DEPLOYMENT, make_app


fake_servers = []
fake_threads = []


def _run_fake(device):
    host, port = device["ip"].split(":")
    config = uvicorn.Config(
        make_app(device), host=host, port=int(port), log_level="error"
    )
    server = uvicorn.Server(config)
    fake_servers.append(server)
    asyncio.run(server.serve())


for d in DEPLOYMENT:
    t = threading.Thread(target=_run_fake, args=(d,), daemon=True)
    t.start()
    fake_threads.append(t)
print(f"  {len(DEPLOYMENT)} fake ESP32 threads started")
time.sleep(1.5)


# ─────────────────────────────────────────────────────────────────
# Start the MCP server in a child process so it has its own loop
# ─────────────────────────────────────────────────────────────────
section("1. Start MCP server in a subprocess")

repo_root = Path(__file__).resolve().parent.parent
mcp_proc = subprocess.Popen(
    [sys.executable, "-m", "mcp_server.server"],
    cwd=str(repo_root),
    env={**os.environ, "PYTHONPATH": str(repo_root)},
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

# Give uvicorn a moment to bind. We poll the port.
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
print(f"  MCP server is up on 127.0.0.1:{MCP_PORT}")


# ─────────────────────────────────────────────────────────────────
# Connect CrewAI's MCPServerAdapter
# ─────────────────────────────────────────────────────────────────
try:
    section("2. CrewAI MCPServerAdapter — list tools")

    from crewai_tools import MCPServerAdapter

    server_params = {
        "url":       f"http://127.0.0.1:{MCP_PORT}/mcp/",
        "transport": "streamable-http",
    }

    with MCPServerAdapter(server_params) as tools:
        tool_names = sorted(t.name for t in tools)
        print(f"  Found {len(tools)} tools:")
        for n in tool_names:
            print(f"    - {n}")

        # ─────────────────────────────────────────────────────────
        section("3. Split tools by prefix")
        from crew.crew import split_tools_by_prefix

        mon_tools, orch_tools = split_tools_by_prefix(tools)
        mon_names  = sorted(t.name for t in mon_tools)
        orch_names = sorted(t.name for t in orch_tools)
        print(f"  monitoring_*    ({len(mon_tools)}): {mon_names}")
        print(f"  orchestration_* ({len(orch_tools)}): {orch_names}")
        assert len(mon_tools)  >= 5, "expected at least 5 monitoring tools"
        assert len(orch_tools) >= 4, "expected at least 4 orchestration tools"

        # ─────────────────────────────────────────────────────────
        section("4. Invoke monitoring_discover_network through CrewAI wrapper")
        discover_tool = next(
            t for t in tools if t.name == "monitoring_discover_network"
        )
        # CrewAI tools expose a .run(...) method that takes kwargs and
        # returns the tool's JSON-encoded result as a string.
        result_str = discover_tool.run(seed_ip="127.0.0.1:9001")
        print(f"  raw result type: {type(result_str).__name__}")
        result = json.loads(result_str) if isinstance(result_str, str) else result_str
        print(f"  ok={result.get('ok')}  count={result.get('count')}")
        for d in result.get("discovered", []):
            print(f"    {d['device_id']:<10} zone={d['location']['zone']}")
        assert result["ok"]
        assert result["count"] == 4

        # ─────────────────────────────────────────────────────────
        section("5. Invoke orchestration_read_devices(zone='corridor')")
        read_tool = next(
            t for t in tools if t.name == "orchestration_read_devices"
        )
        result_str = read_tool.run(zone="corridor")
        result = json.loads(result_str) if isinstance(result_str, str) else result_str
        print(f"  count={result['count']}")
        for d in result["devices"]:
            print(f"    {d['device_id']} services={[s['name'] for s in d['services']]}")
        assert result["count"] == 2

        # ─────────────────────────────────────────────────────────
        section("6. Build the two CrewAI agents (without running them)")
        from crew.agents import build_monitoring_agent, build_orchestration_agent

        monitoring_agent    = build_monitoring_agent(mon_tools)
        orchestration_agent = build_orchestration_agent(orch_tools)
        print(f"  monitoring_agent.role    = {monitoring_agent.role!r}")
        print(f"  orchestration_agent.role = {orchestration_agent.role!r}")
        print(f"  orchestration_agent.allow_delegation = "
              f"{orchestration_agent.allow_delegation}")

        # ─────────────────────────────────────────────────────────
        section("7. Build the Crew (no LLM call yet)")
        from crewai import Crew, Process
        from crew.tasks import build_orchestration_task
        task = build_orchestration_task(orchestration_agent)
        crew = Crew(
            agents=[monitoring_agent, orchestration_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )
        print(f"  crew has {len(crew.agents)} agents and {len(crew.tasks)} task(s)")

    print()
    print("═" * 70)
    print("  ALL CONNECTION TESTS PASSED")
    print("  (the actual LLM kickoff requires Ollama running with llama3.1)")
    print("═" * 70)

finally:
    mcp_proc.terminate()
    try:
        mcp_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        mcp_proc.kill()
