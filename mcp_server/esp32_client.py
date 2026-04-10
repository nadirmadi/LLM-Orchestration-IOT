"""
esp32_client.py — Thin async HTTP client used by the Monitoring tools
to interrogate ESP32 devices and by the Orchestration tools to send
commands to them.

All ESP32s expose the same minimal HTTP surface (see the firmware in
esp32_fixe_firmware/):

    GET  /capabilities  -> { device_id, ip, status, location,
                             services, neighbors }
    GET  /health        -> { status, battery, rssi, ... }
    POST /wake          -> {} (transition to active)
    POST /sleep         -> {} (transition to light_sleep)
    POST /activate_service  -> { "service": "camera" }
"""

import httpx
from typing import Optional


DEFAULT_TIMEOUT = 5.0


class ESP32Client:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    # ─── reads ────────────────────────────────────────────────────
    async def get_capabilities(self, ip: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.get(f"http://{ip}/capabilities")
            r.raise_for_status()
            return r.json()

    async def get_health(self, ip: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.get(f"http://{ip}/health")
            r.raise_for_status()
            return r.json()

    # ─── writes ───────────────────────────────────────────────────
    async def wake(self, ip: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.post(f"http://{ip}/wake")
            r.raise_for_status()
            return r.json() if r.content else {"ok": True}

    async def sleep(self, ip: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.post(f"http://{ip}/sleep")
            r.raise_for_status()
            return r.json() if r.content else {"ok": True}

    async def activate_service(self, ip: str, service_name: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.post(
                f"http://{ip}/activate_service",
                json={"service": service_name},
            )
            r.raise_for_status()
            return r.json() if r.content else {"ok": True}
