"""
test_discovery.py — End-to-end test of mesh discovery + tools.

Prerequisites:
    1. Start the fake ESP32 deployment in another terminal:
        python -m scripts.fake_esp32

    2. Then run this test:
        python -m scripts.test_discovery

What it does:
    - Cleans up the test database
    - Calls monitoring_tools.discover_network with the seed esp32-001
    - Verifies that all 4 fakes are discovered and persisted
    - Calls monitoring_tools.read_devices(zone="corridor") to validate
      the canonical JSON shape
    - Calls orchestration_tools.wake_up_device("esp32-002")
    - Calls orchestration_tools.activate_service("esp32-002", "camera")
    - Calls orchestration_tools.put_device_to_sleep("esp32-002")
"""

import os
import json
import asyncio
import tempfile

# Use a throwaway database
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "llmthings_disco_test.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

from database import init_db                                # noqa: E402
from mcp_server.tools import monitoring_tools, orchestration_tools  # noqa: E402


def section(title: str):
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


async def main():
    section("0. Init DB")
    init_db()

    # ─────────────────────────────────────────────────────────────
    section("1. Mesh discovery from seed esp32-001 (127.0.0.1:9001)")
    result = await monitoring_tools.discover_network("127.0.0.1:9001")

    if not result["ok"]:
        print(f"  FAILED: {result.get('error')}")
        print("  Did you start `python -m scripts.fake_esp32` first?")
        return

    print(f"  Discovered {result['count']} devices")
    for d in result["discovered"]:
        print(f"    {d['device_id']:<10} zone={d['location']['zone']:<14} "
              f"services={[s['name'] for s in d['services']]}")
    if result["failed"]:
        print(f"  Failed probes: {result['failed']}")

    # ─────────────────────────────────────────────────────────────
    section("2. monitoring_read_devices(zone='corridor')")
    devices = monitoring_tools.read_devices(zone="corridor")
    print(json.dumps(devices, indent=2, ensure_ascii=False))

    # ─────────────────────────────────────────────────────────────
    section("3. orchestration_wake_up_device('esp32-002')")
    r = await orchestration_tools.wake_up_device("esp32-002")
    print(json.dumps(r, indent=2))

    # ─────────────────────────────────────────────────────────────
    section("4. orchestration_activate_service('esp32-002', 'camera')")
    r = await orchestration_tools.activate_service("esp32-002", "camera")
    print(json.dumps(r, indent=2))

    # ─────────────────────────────────────────────────────────────
    section("5. orchestration_put_device_to_sleep('esp32-002')")
    r = await orchestration_tools.put_device_to_sleep("esp32-002")
    print(json.dumps(r, indent=2))

    # ─────────────────────────────────────────────────────────────
    section("6. monitoring_get_health('esp32-003')")
    r = await monitoring_tools.get_health("esp32-003")
    print(json.dumps(r, indent=2))

    print()
    print("All end-to-end tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
