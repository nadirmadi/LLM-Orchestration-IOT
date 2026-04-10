"""
orchestration_tools.py — MCP tools used by the Orchestration Agent.

Strict policy:
  - The Orchestration Agent has READ-ONLY access to the database
    (via read_devices). It cannot upsert or delete.
  - It can issue COMMANDS to ESP32 devices: wake, sleep, activate_service.
    After a command, it asks the Monitoring Agent to refresh the device
    via get_health (or it can refresh the local DB status itself, since
    "current status of a device" is a fact, not a write of new knowledge).
"""

from typing import Optional

from database import (
    get_device,
    query_devices,
    update_device_status,
)
from mcp_server.esp32_client import ESP32Client


client = ESP32Client()


# ─────────────────────────────────────────────────────────────────
# 1. Read-only DB access
# ─────────────────────────────────────────────────────────────────
def read_devices(
    zone:        Optional[str] = None,
    service:     Optional[str] = None,
    status:      Optional[str] = None,
    device_type: Optional[str] = None,
) -> dict:
    """Same shape as monitoring_tools.read_devices, but no write hooks."""
    devices = query_devices(
        zone=zone,
        service=service,
        status=status,
        device_type=device_type,
    )
    return {"count": len(devices), "devices": devices}


# ─────────────────────────────────────────────────────────────────
# 2. Commands sent to physical devices
# ─────────────────────────────────────────────────────────────────
async def wake_up_device(device_id: str) -> dict:
    """Wake a device that is currently in light_sleep."""
    d = get_device(device_id)
    if d is None:
        return {"ok": False, "error": f"device {device_id} not in database"}

    try:
        await client.wake(d["ip"])
        update_device_status(device_id, "active")
        return {"ok": True, "device_id": device_id, "new_status": "active"}
    except Exception as e:
        return {"ok": False, "device_id": device_id, "error": str(e)}


async def put_device_to_sleep(device_id: str) -> dict:
    """Send a device back into light_sleep to save energy."""
    d = get_device(device_id)
    if d is None:
        return {"ok": False, "error": f"device {device_id} not in database"}

    try:
        await client.sleep(d["ip"])
        update_device_status(device_id, "light_sleep")
        return {"ok": True, "device_id": device_id, "new_status": "light_sleep"}
    except Exception as e:
        return {"ok": False, "device_id": device_id, "error": str(e)}


async def activate_service(device_id: str, service_name: str) -> dict:
    """Tell a device to start a specific service (e.g. start streaming
    its camera). The device must already be active."""
    d = get_device(device_id)
    if d is None:
        return {"ok": False, "error": f"device {device_id} not in database"}

    # Sanity check: the requested service must actually be exposed
    available = {s["name"] for s in d.get("services", [])}
    if service_name not in available:
        return {
            "ok": False,
            "device_id": device_id,
            "error": f"device does not expose service '{service_name}'",
            "available_services": sorted(available),
        }

    try:
        result = await client.activate_service(d["ip"], service_name)
        return {
            "ok": True,
            "device_id": device_id,
            "service": service_name,
            "result": result,
        }
    except Exception as e:
        return {"ok": False, "device_id": device_id, "error": str(e)}
