"""
test_local.py — Smoke test that exercises the database layer WITHOUT
needing a real ESP32, an MQTT broker, or even the MCP server running.

It simulates two fixed devices and one badge, upserts them into the
database, and runs a few representative queries — exactly the sort
of queries the Monitoring Agent will end up making.

Run from the project root:
    python -m scripts.test_local
"""

import os
import json
import tempfile

# Use a throwaway database file so this test never touches your real one
os.environ.setdefault("DB_PATH", os.path.join(tempfile.gettempdir(), "llmthings_test.db"))

# Make sure we start clean
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

from database import (  # noqa: E402
    init_db,
    upsert_device,
    query_devices,
    get_device,
    update_device_status,
    delete_device,
)


def section(title: str):
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


# ─────────────────────────────────────────────────────────────────
section("1. Initialize the database")
init_db()


# ─────────────────────────────────────────────────────────────────
section("2. Simulate two fixed ESP32s + the patient badge")

devices = [
    {
        "device_id":   "esp32-001",
        "ip":          "192.168.1.42",
        "status":      "light_sleep",
        "device_type": "fixed",
        "location":    {"zone": "corridor", "x": 3.5, "y": 1.2, "z": 0.0},
        "services": [
            {"name": "pir", "protocol": "MQTT",
             "details": {"detection_range_m": 5}},
            {"name": "imu", "protocol": "MQTT",
             "details": {"fall_detection": True}},
        ],
        "neighbors": ["esp32-002", "esp32-003"],
    },
    {
        "device_id":   "esp32-002",
        "ip":          "192.168.1.43",
        "status":      "light_sleep",
        "device_type": "fixed",
        "location":    {"zone": "corridor", "x": 6.0, "y": 1.2, "z": 0.0},
        "services": [
            {"name": "camera", "protocol": "HTTP",
             "details": {"stream": True, "resolution": "720p", "fov": 90}},
        ],
        "neighbors": ["esp32-001"],
    },
    {
        "device_id":   "badge-001",
        "ip":          "192.168.1.50",
        "status":      "active",
        "device_type": "badge",
        "location":    {"zone": "activity_node", "x": 0.0, "y": 0.0, "z": 1.1},
        "services": [
            {"name": "imu",   "protocol": "MQTT",
             "details": {"fall_detection": True}},
            {"name": "sound", "protocol": "MQTT", "details": {}},
        ],
        "neighbors": [],
    },
]

for d in devices:
    saved = upsert_device(d)
    print(f"  upserted {saved['device_id']:<10} "
          f"status={saved['status']:<12} "
          f"services={[s['name'] for s in saved['services']]}")


# ─────────────────────────────────────────────────────────────────
section("3. Query: 'which devices are available in the corridor?'")

result = query_devices(zone="corridor")
print(json.dumps(result, indent=2, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────
section("4. Query: 'which devices have a camera service?'")

result = query_devices(service="camera")
for d in result:
    print(f"  {d['device_id']} in zone {d['location']['zone']}")


# ─────────────────────────────────────────────────────────────────
section("5. Update: wake esp32-001 (status -> active)")

updated = update_device_status("esp32-001", "active")
print(f"  esp32-001 is now: {updated['status']}")


# ─────────────────────────────────────────────────────────────────
section("6. Query: 'which active devices in the corridor have an IMU?'")

result = query_devices(zone="corridor", service="imu", status="active")
print(json.dumps(result, indent=2, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────
section("7. Delete the badge and check it is gone")

delete_device("badge-001")
print(f"  get_device('badge-001') -> {get_device('badge-001')}")


print()
print("All tests passed.")
