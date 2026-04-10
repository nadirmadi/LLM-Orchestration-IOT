"""
monitoring_tools.py — MCP tools used by the Monitoring Agent.

These tools cover three concerns:
  1. Mesh discovery     — walk the neighbors graph from a seed device.
  2. Per-device probes  — get_capabilities / get_health on demand.
  3. Database access    — read AND write (only the Monitoring Agent
                          is allowed to write).

All other agents (Orchestration, etc.) get a read-only subset via
orchestration_tools.py.
"""

import os
from typing import Optional

from database import (
    upsert_device,
    get_device,
    get_all_devices,
    query_devices,
    update_device_status,
)
from mcp_server.esp32_client import ESP32Client


client = ESP32Client()


# ─────────────────────────────────────────────────────────────────
# 1. Mesh discovery
# ─────────────────────────────────────────────────────────────────
async def discover_network(seed_ip: Optional[str] = None) -> dict:
    """Walk the deployment graph starting from a known device IP.

    Algorithm:
        1. GET /capabilities on the seed
        2. Save it to the database
        3. For each neighbor in the response (each carries its own IP),
           recurse if not already visited.
        4. Return the list of discovered devices.

    The seed IP defaults to the SEED_DEVICE_IP environment variable.

    /capabilities response shape expected from the firmware:
        {
          "device_id": "esp32-001",
          "ip": "...",
          "status": "...",
          "location": {...},
          "services": [...],
          "neighbors": [
            {"device_id": "esp32-002", "ip": "192.168.1.43"},
            ...
          ]
        }
    """
    if seed_ip is None:
        seed_ip = os.getenv("SEED_DEVICE_IP")
    if not seed_ip:
        return {
            "ok": False,
            "error": "no seed IP provided and SEED_DEVICE_IP not set",
        }

    visited_ids: set[str] = set()
    visited_ips: set[str] = set()
    discovered: list[dict] = []
    failed: list[dict]    = []

    async def walk(ip: str):
        if ip in visited_ips:
            return
        visited_ips.add(ip)

        try:
            caps = await client.get_capabilities(ip)
        except Exception as e:
            failed.append({"ip": ip, "error": str(e)})
            return

        device_id = caps.get("device_id")
        if not device_id or device_id in visited_ids:
            return
        visited_ids.add(device_id)

        # Persist into the database (Monitoring Agent's write privilege).
        # upsert_device understands neighbors as either bare IDs or {id,ip}
        # objects — see device_registry.upsert_device.
        saved = upsert_device(caps)
        discovered.append(saved)

        # Recurse on neighbors using THEIR IPs (carried in the payload).
        for n in caps.get("neighbors", []):
            n_ip = n["ip"] if isinstance(n, dict) else None
            if n_ip and n_ip not in visited_ips:
                await walk(n_ip)

    await walk(seed_ip)

    return {
        "ok":         True,
        "seed":       seed_ip,
        "discovered": discovered,
        "failed":     failed,
        "count":      len(discovered),
    }


# ─────────────────────────────────────────────────────────────────
# 2. Per-device probes
# ─────────────────────────────────────────────────────────────────
async def get_capabilities(ip: str) -> dict:
    """Pull the /capabilities endpoint of a single ESP32 and persist it."""
    try:
        caps  = await client.get_capabilities(ip)
        saved = upsert_device(caps)
        return {"ok": True, "device": saved}
    except Exception as e:
        return {"ok": False, "ip": ip, "error": str(e)}


async def get_health(device_id: str) -> dict:
    """Call GET /health on a known device. The device's IP is read from the
    database, so the Monitoring Agent must have discovered it first."""
    d = get_device(device_id)
    if d is None:
        return {"ok": False, "error": f"device {device_id} not in database"}

    try:
        health = await client.get_health(d["ip"])
        # If the health probe succeeds, we know the device is reachable.
        # We refresh the status if the device claimed something more precise.
        new_status = health.get("status")
        if new_status:
            update_device_status(device_id, new_status)
        return {"ok": True, "device_id": device_id, "health": health}
    except Exception as e:
        # Probe failed: mark the device as inactive.
        update_device_status(device_id, "inactive")
        return {"ok": False, "device_id": device_id, "error": str(e)}


# ─────────────────────────────────────────────────────────────────
# 3. Database operations
# ─────────────────────────────────────────────────────────────────
def read_devices(
    zone:        Optional[str] = None,
    service:     Optional[str] = None,
    status:      Optional[str] = None,
    device_type: Optional[str] = None,
) -> dict:
    """Read the deployment state from the database with optional filters.

    Returns the canonical JSON shape (the same the Monitoring Agent will
    forward to the Orchestration Agent in their natural-language dialogue).
    """
    devices = query_devices(
        zone=zone,
        service=service,
        status=status,
        device_type=device_type,
    )
    return {"count": len(devices), "devices": devices}


def write_device(device_payload: dict) -> dict:
    """Manual upsert. Used in tests and as an escape hatch."""
    saved = upsert_device(device_payload)
    return {"ok": True, "device": saved}
