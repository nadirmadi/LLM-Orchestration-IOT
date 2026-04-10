"""
test_e2e_combined.py — Runs the fake ESP32 deployment and the discovery
test in the same process. This avoids needing background processes,
which is convenient when working in an environment that does not
preserve background jobs across shell commands.

Run from project root:
    python -m scripts.test_e2e_combined
"""

import os
import json
import asyncio
import tempfile

# Use a throwaway database
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "llmthings_e2e.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

import uvicorn

from database import init_db
from scripts.fake_esp32 import DEPLOYMENT, make_app
from mcp_server.tools import monitoring_tools, orchestration_tools


def section(title: str):
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


async def start_fake_servers():
    """Spin up uvicorn for each fake device, return the server tasks."""
    servers = []
    for device in DEPLOYMENT:
        host, port = device["ip"].split(":")
        config = uvicorn.Config(
            make_app(device), host=host, port=int(port),
            log_level="error",
        )
        server = uvicorn.Server(config)
        servers.append(server)

    tasks = [asyncio.create_task(s.serve()) for s in servers]
    # Give uvicorn a beat to actually bind the sockets
    await asyncio.sleep(1.0)
    return servers, tasks


async def stop_fake_servers(servers, tasks):
    for s in servers:
        s.should_exit = True
    await asyncio.sleep(0.2)
    for t in tasks:
        if not t.done():
            t.cancel()


async def main():
    section("0. Init DB and start 4 fake ESP32s")
    init_db()
    servers, tasks = await start_fake_servers()
    print(f"  {len(servers)} fake devices listening on 127.0.0.1:9001..9004")

    try:
        # ─────────────────────────────────────────────────────────
        section("1. Mesh discovery from seed esp32-001")
        result = await monitoring_tools.discover_network("127.0.0.1:9001")
        if not result["ok"]:
            print(f"  FAILED: {result.get('error')}")
            return

        print(f"  Discovered {result['count']} devices "
              f"(failed: {len(result['failed'])})")
        for d in result["discovered"]:
            print(f"    {d['device_id']:<10} "
                  f"zone={d['location']['zone']:<14} "
                  f"services={[s['name'] for s in d['services']]} "
                  f"neighbors={d['neighbors']}")

        assert result["count"] == 4, f"Expected 4 devices, got {result['count']}"
        print("  OK — all 4 devices discovered via mesh recursion")

        # ─────────────────────────────────────────────────────────
        section("2. monitoring_read_devices(zone='corridor')")
        devices = monitoring_tools.read_devices(zone="corridor")
        print(f"  Found {devices['count']} devices in corridor")
        for d in devices["devices"]:
            print(f"    {d['device_id']} services={[s['name'] for s in d['services']]}")
        assert devices["count"] == 2

        # ─────────────────────────────────────────────────────────
        section("3. orchestration_read_devices(service='camera')")
        devices = orchestration_tools.read_devices(service="camera")
        print(f"  Found {devices['count']} devices with a camera service")
        for d in devices["devices"]:
            print(f"    {d['device_id']} in zone {d['location']['zone']}")
        assert devices["count"] == 2

        # ─────────────────────────────────────────────────────────
        section("4. orchestration_wake_up_device('esp32-002')")
        r = await orchestration_tools.wake_up_device("esp32-002")
        print(f"  {r}")
        assert r["ok"]
        assert r["new_status"] == "active"

        # ─────────────────────────────────────────────────────────
        section("5. orchestration_activate_service('esp32-002', 'camera')")
        r = await orchestration_tools.activate_service("esp32-002", "camera")
        print(f"  {r}")
        assert r["ok"]

        # ─────────────────────────────────────────────────────────
        section("6. orchestration_activate_service('esp32-002', 'microwave')")
        print("  (should fail because the device does not expose 'microwave')")
        r = await orchestration_tools.activate_service("esp32-002", "microwave")
        print(f"  {r}")
        assert not r["ok"]
        assert "available_services" in r

        # ─────────────────────────────────────────────────────────
        section("7. monitoring_get_health('esp32-003')")
        r = await monitoring_tools.get_health("esp32-003")
        print(f"  {r}")
        assert r["ok"]
        assert r["health"]["device"] == "esp32-003"

        # ─────────────────────────────────────────────────────────
        section("8. orchestration_put_device_to_sleep('esp32-002')")
        r = await orchestration_tools.put_device_to_sleep("esp32-002")
        print(f"  {r}")
        assert r["ok"]
        assert r["new_status"] == "light_sleep"

        # ─────────────────────────────────────────────────────────
        section("9. Final state — full deployment")
        all_devices = monitoring_tools.read_devices()
        print(f"  {all_devices['count']} devices in DB")
        for d in all_devices["devices"]:
            print(f"    {d['device_id']:<10} "
                  f"status={d['status']:<12} "
                  f"zone={d['location']['zone']}")

        print()
        print("═" * 64)
        print("  ALL END-TO-END TESTS PASSED")
        print("═" * 64)

    finally:
        await stop_fake_servers(servers, tasks)


if __name__ == "__main__":
    asyncio.run(main())
