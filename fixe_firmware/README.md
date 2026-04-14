# Deploying the 3-node mesh: badge + ultrasonic + camera

This guide walks you through flashing the three ESP32 firmwares and
validating the mesh discovery end-to-end from the MCP server.

## 1. Assign each device a fixed IP in your router

Mesh discovery uses hardcoded neighbor IPs. Either reserve fixed DHCP
leases in your router admin, or update the IPs in the firmware after
each flash. The firmwares currently assume:

| Device            | Hardcoded IP    | Firmware folder                             |
| ----------------- | --------------- | ------------------------------------------- |
| `badge-001`       | `192.168.1.50`  | `badge_firmware/badge-patient/`             |
| `esp32-fixe-001`  | `192.168.1.51`  | `fixe_firmware/esp32-fixe-001/`             |
| `esp32-cam-001`   | `192.168.1.52`  | `fixe_firmware/cam/esp32-cam-001/`          |

If your router hands out different IPs, edit **all three** `HttpAdapter.cpp`
files — each node references the other two in its `neighbors` list, so
they all need to know each other's IP.

## 2. Edit WiFi credentials in each .ino

- `badge_firmware/badge-patient/badge-patient.ino`
- `fixe_firmware/esp32-fixe-001/esp32-fixe-001.ino`
- `fixe_firmware/cam/esp32-cam-001/esp32-cam-001.ino`

All three must be on the **same WiFi network** as the machine running
`docker compose` (the MCP server container needs to reach them).

## 3. Set the broker IP in MqttAdapter.cpp

Only the badge and the ultrasonic node publish MQTT. Update the broker IP
in:

- `badge_firmware/badge-patient/MqttAdapter.cpp`
- `fixe_firmware/esp32-fixe-001/MqttAdapter.cpp`

Use the IP of the machine running `docker compose` (find it with
`hostname -I` on Linux). The ESP32-CAM does not publish MQTT.

## 4. Flash each device

One at a time in the Arduino IDE. Check the serial monitor for:

```
[WiFi] Connected — IP: 192.168.1.XX
[HTTP] ... ready (MCP-compatible)
```

If the IP is different from what you expected, either fix the DHCP
lease or re-edit the neighbor IPs in all three firmwares.

## 5. Validate each node individually from your laptop

```bash
curl http://192.168.1.50/capabilities   # badge
curl http://192.168.1.51/capabilities   # ultrasonic
curl http://192.168.1.52/capabilities   # camera
```

Each should return a JSON object with `device_id`, `services`, and a
`neighbors` array referencing the other two nodes.

## 6. Run full-mesh discovery from the MCP server

From any seed, the Monitoring Agent should discover all three nodes.
Try from the badge as seed:

```bash
docker compose --profile dockered-ollama run --rm crew python -c "
import asyncio
from mcp_server.tools.monitoring_tools import discover_network
r = asyncio.run(discover_network('192.168.1.50:80'))
print(f\"discovered {r['count']} devices:\")
for d in r['discovered']:
    print(f\"  {d['device_id']:<18} zone={d['location']['zone']:<10} \"
          f\"services={[s['name'] for s in d['services']]}\")
"
```

Expected output:
```
discovered 3 devices:
  badge-001         zone=on_patient  services=['imu', 'sound']
  esp32-cam-001     zone=corridor    services=['camera']
  esp32-fixe-001    zone=corridor    services=['ultrasonic']
```

## 7. Run the crew with a scenario that uses all three

```bash
docker compose --profile dockered-ollama run --rm crew bash -c '
BADGE_IP=192.168.1.50 python -m scripts.test_crew_real_badge'
```

With three devices now in the database, the agents can reason about
richer scenarios like "what is currently available in the corridor?"
or "activate the camera to check on the patient".

## Cross-machine setup (badge on one laptop, fixes on another)

If the badge is plugged into your laptop and the two fixed ESP32s are
plugged into another laptop, **this does not matter for the mesh** as
long as all three are on the **same WiFi**. They all speak HTTP on
their own IPs; the laptops are only used for power and flashing.

The Docker stack runs on exactly one of the two laptops — the one that
runs the MCP server, broker, and crew. The ESP32s only need to see
this laptop's IP (for MQTT) and each other (for mesh).
