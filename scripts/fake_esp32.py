"""
fake_esp32.py — Lightweight simulator of an ESP32 device.

Spawns N fake ESP32s, each on its own port, exposing the same HTTP
endpoints that the real firmware will expose:

    GET  /capabilities       -> the canonical device JSON
    GET  /health             -> { status, battery, rssi }
    POST /wake               -> sets in-memory status to "active"
    POST /sleep              -> sets in-memory status to "light_sleep"
    POST /activate_service   -> { "service": "..." }

This lets you exercise the entire MCP server (including
monitoring_discover_network) end-to-end without any real hardware.

Usage:
    # In one terminal
    python -m scripts.fake_esp32

    # In another terminal — point the MCP server's SEED_DEVICE_IP
    # at one of the fakes (e.g. 127.0.0.1:9001) and run the test
    python -m scripts.test_discovery
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn


# ─────────────────────────────────────────────────────────────────
# Define a small fake deployment: 4 devices wired into a line
#   esp32-001 <-> esp32-002 <-> esp32-003 <-> esp32-004
# ─────────────────────────────────────────────────────────────────
DEPLOYMENT = [
    {
        "device_id":   "esp32-001",
        "ip":          "127.0.0.1:9001",
        "status":      "light_sleep",
        "device_type": "fixed",
        "location":    {"zone": "activity_node", "x": 1.0, "y": 1.0, "z": 0.0},
        "services": [
            {"name": "pir", "protocol": "MQTT",
             "details": {"detection_range_m": 5}},
        ],
        # Neighbors carry both their device_id AND their IP, so the
        # Monitoring Agent's mesh-discovery can follow the link without
        # needing the database to already know about them.
        "neighbors": [
            {"device_id": "esp32-002", "ip": "127.0.0.1:9002"},
        ],
    },
    {
        "device_id":   "esp32-002",
        "ip":          "127.0.0.1:9002",
        "status":      "light_sleep",
        "device_type": "fixed",
        "location":    {"zone": "corridor", "x": 4.0, "y": 1.0, "z": 0.0},
        "services": [
            {"name": "pir",    "protocol": "MQTT",
             "details": {"detection_range_m": 5}},
            {"name": "camera", "protocol": "HTTP",
             "details": {"stream": True, "resolution": "720p", "fov": 90}},
        ],
        "neighbors": [
            {"device_id": "esp32-001", "ip": "127.0.0.1:9001"},
            {"device_id": "esp32-003", "ip": "127.0.0.1:9003"},
        ],
    },
    {
        "device_id":   "esp32-003",
        "ip":          "127.0.0.1:9003",
        "status":      "light_sleep",
        "device_type": "fixed",
        "location":    {"zone": "corridor", "x": 7.0, "y": 1.0, "z": 0.0},
        "services": [
            {"name": "imu", "protocol": "MQTT",
             "details": {"fall_detection": True}},
        ],
        "neighbors": [
            {"device_id": "esp32-002", "ip": "127.0.0.1:9002"},
            {"device_id": "esp32-004", "ip": "127.0.0.1:9004"},
        ],
    },
    {
        "device_id":   "esp32-004",
        "ip":          "127.0.0.1:9004",
        "status":      "light_sleep",
        "device_type": "fixed",
        "location":    {"zone": "kitchen", "x": 10.0, "y": 1.0, "z": 0.0},
        "services": [
            {"name": "camera", "protocol": "HTTP",
             "details": {"stream": True, "resolution": "1080p", "fov": 120}},
        ],
        "neighbors": [
            {"device_id": "esp32-003", "ip": "127.0.0.1:9003"},
        ],
    },
]


# ─────────────────────────────────────────────────────────────────
# One FastAPI app per fake device
# ─────────────────────────────────────────────────────────────────
def make_app(device: dict) -> FastAPI:
    app = FastAPI(title=f"fake-{device['device_id']}")

    # Mutable in-memory state for this device
    state = {"status": device["status"]}

    @app.get("/capabilities")
    def capabilities():
        return {**device, "status": state["status"]}

    @app.get("/health")
    def health():
        return {
            "status":  state["status"],
            "battery": 87,
            "rssi":    -52,
            "device":  device["device_id"],
        }

    @app.post("/wake")
    def wake():
        state["status"] = "active"
        return {"ok": True, "new_status": state["status"]}

    @app.post("/sleep")
    def sleep():
        state["status"] = "light_sleep"
        return {"ok": True, "new_status": state["status"]}

    @app.post("/activate_service")
    async def activate_service(request: Request):
        body = await request.json()
        service_name = body.get("service")
        return {
            "ok":      True,
            "service": service_name,
            "status":  state["status"],
        }

    return app


# ─────────────────────────────────────────────────────────────────
# Boot all fakes in parallel
# ─────────────────────────────────────────────────────────────────
async def run_one(device: dict):
    host, port = device["ip"].split(":")
    app = make_app(device)
    config = uvicorn.Config(
        app, host=host, port=int(port), log_level="warning"
    )
    server = uvicorn.Server(config)
    print(f"  fake {device['device_id']:<10} -> http://{device['ip']}")
    await server.serve()


async def main():
    print("Starting fake ESP32 deployment...")
    await asyncio.gather(*(run_one(d) for d in DEPLOYMENT))


if __name__ == "__main__":
    asyncio.run(main())
