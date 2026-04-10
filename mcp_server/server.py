"""
server.py — MCP HTTP server exposing the Monitoring and Orchestration
tool sets to the CrewAI agents.

We use FastMCP from the official `mcp` Python SDK. FastMCP discovers
tools from decorated Python functions and exposes them either over
stdio or — as we want here — over a streamable HTTP transport so that
remote clients (CrewAI agents in other containers) can connect to it.

Run:
    uvicorn-style:  python -m mcp_server.server
    Docker:         see docker-compose.yml

Environment variables:
    DB_PATH         path to the SQLite file        (default: /data/monitoring.db)
    SEED_DEVICE_IP  seed for mesh discovery        (no default — must be set)
    MCP_HOST        host to bind                   (default: 0.0.0.0)
    MCP_PORT        port to bind                   (default: 8765)
"""

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from database import init_db
from mcp_server.tools import monitoring_tools, orchestration_tools


# ─────────────────────────────────────────────────────────────────
# Initialize the database before starting the server
# ─────────────────────────────────────────────────────────────────
init_db()


# ─────────────────────────────────────────────────────────────────
# FastMCP instance
# ─────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="llmthings-monitoring",
    instructions=(
        "Tools for the LLMThings IoT deployment. Tools prefixed with "
        "`monitoring_` are reserved for the Monitoring Agent (read+write). "
        "Tools prefixed with `orchestration_` are for the Orchestration "
        "Agent (read-only DB + device commands)."
    ),
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8765")),
    # stateless_http avoids "session not found" errors when CrewAI makes
    # several tool calls in a row over streamable HTTP. Each request is
    # self-contained and not bound to a specific server replica/session.
    stateless_http=True,
)


# ─────────────────────────────────────────────────────────────────
# Monitoring tools
# ─────────────────────────────────────────────────────────────────
@mcp.tool()
async def monitoring_discover_network(seed_ip: Optional[str] = None) -> dict:
    """Walk the deployment graph from a known seed ESP32 and persist all
    discovered devices in the database. If `seed_ip` is omitted, the
    SEED_DEVICE_IP environment variable is used.
    """
    return await monitoring_tools.discover_network(seed_ip)


@mcp.tool()
async def monitoring_get_capabilities(ip: str) -> dict:
    """Pull the /capabilities endpoint of one ESP32 by IP and persist the
    result. Use this to refresh a single device without doing a full
    network discovery."""
    return await monitoring_tools.get_capabilities(ip)


@mcp.tool()
async def monitoring_get_health(device_id: str) -> dict:
    """Call GET /health on a known device. If the probe fails, the device
    is automatically marked as inactive in the database."""
    return await monitoring_tools.get_health(device_id)


@mcp.tool()
def monitoring_read_devices(
    zone:        Optional[str] = None,
    service:     Optional[str] = None,
    status:      Optional[str] = None,
    device_type: Optional[str] = None,
) -> dict:
    """Read the deployment state from the database. All filters are
    optional and combined with AND.

    Example: zone='corridor', service='camera' returns every active
    device in the corridor that exposes a camera service.
    """
    return monitoring_tools.read_devices(
        zone=zone,
        service=service,
        status=status,
        device_type=device_type,
    )


@mcp.tool()
def monitoring_write_device(device_payload: dict) -> dict:
    """Manually upsert a device. Useful for tests or for seeding the
    database before any discovery has run."""
    return monitoring_tools.write_device(device_payload)


# ─────────────────────────────────────────────────────────────────
# Orchestration tools
# ─────────────────────────────────────────────────────────────────
@mcp.tool()
def orchestration_read_devices(
    zone:        Optional[str] = None,
    service:     Optional[str] = None,
    status:      Optional[str] = None,
    device_type: Optional[str] = None,
) -> dict:
    """Read-only view of the deployment for the Orchestration Agent.
    Same shape as `monitoring_read_devices` but without write access."""
    return orchestration_tools.read_devices(
        zone=zone,
        service=service,
        status=status,
        device_type=device_type,
    )


@mcp.tool()
async def orchestration_wake_up_device(device_id: str) -> dict:
    """Wake an ESP32 currently in light_sleep. The device's IP is read
    from the database — discover the network first if it is not there."""
    return await orchestration_tools.wake_up_device(device_id)


@mcp.tool()
async def orchestration_put_device_to_sleep(device_id: str) -> dict:
    """Send an active device back into light_sleep to save energy."""
    return await orchestration_tools.put_device_to_sleep(device_id)


@mcp.tool()
async def orchestration_activate_service(device_id: str, service_name: str) -> dict:
    """Tell an active device to start one of its services (for example
    start streaming its camera). The device must already be active."""
    return await orchestration_tools.activate_service(device_id, service_name)


# ─────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[MCP] Starting LLMThings MCP server on "
          f"{mcp.settings.host}:{mcp.settings.port}")
    # streamable-http is the modern HTTP transport supported by CrewAI
    mcp.run(transport="streamable-http")
