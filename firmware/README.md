# Firmware — 3 devices

Three independent firmwares for the LLMThings v2 deployment:

```
firmware/
├── badge-patient/      # patient badge (IMU + sound, always active, MQTT + HTTP)
├── esp32-fixe-001/     # fixed node with ultrasonic sensor (corridor)
└── esp32-cam-001/      # fixed ESP32-CAM (corridor)
```

All three follow the same MCP contract (same endpoint names, same
canonical JSON shape for `/capabilities`). A single `discover_network`
call walks the entire mesh and populates the DB.

---

## Topology

```
  [ badge-001 ]            on_patient zone
        ^
        |
  [ esp32-cam-001 ]        corridor (camera, high)
        ^
        |
  [ esp32-fixe-001 ]       corridor (ultrasonic, floor-level)
```

The neighbors list hard-coded in each firmware is:

| Device           | Declared neighbors                       |
|------------------|------------------------------------------|
| badge-001        | (none — badge is mobile)                 |
| esp32-fixe-001   | esp32-cam-001                            |
| esp32-cam-001    | esp32-fixe-001, badge-001                |

So seeding the discovery from `esp32-cam-001` reaches everyone.

---

## Two-step deployment procedure

Because DHCP hands out fresh IPs every WiFi session, we don't hard-code
IPs in the firmware. Instead:

### Step 1 — flash and collect IPs

Flash each firmware on its own ESP32 board. Each one will connect to
WiFi and print its IP in the Arduino Serial Monitor:

```
[WiFi] Connected — IP: 192.168.1.50
[HTTP] http://192.168.1.50
```

Write down the three IPs — one per device.

### Step 2 — teach each device who its neighbors are

From the project root (on the PC running Docker):

```bash
python -m scripts.bootstrap_mesh \
    --badge 192.168.1.50 \
    --fixe  192.168.1.51 \
    --cam   192.168.1.52
```

The script POSTs `/set_neighbor` to each ESP so they each learn their
neighbors' runtime IPs. After that, `curl <device-ip>/capabilities`
will return a `neighbors` array populated with proper IDs AND IPs, and
the mesh discovery traversal will work.

### Step 3 — run discovery through the mesh

Use any device as the seed. The cam is the most connected one:

```bash
python -m scripts.bootstrap_mesh \
    --discover-from 192.168.1.52
```

or from inside the crew container:

```bash
docker compose --profile dockered-ollama run --rm crew \
    python -c "
import asyncio
from mcp_server.tools.monitoring_tools import discover_network
print(asyncio.run(discover_network('192.168.1.52:80')))
"
```

You should see all 3 devices discovered and stored in the DB.

---

## What was changed in the received firmware

The code received from the team was good (proper MCP contract, clean
services/adapters separation). Two things were refined:

1. **Dynamic neighbors**: the original `esp32-cam-001` had a
   `REPLACE_WITH_ULTRASONIC_IP` placeholder. Replaced with a runtime
   IP table (`neighborIps[]`) filled by `POST /set_neighbor`. This
   makes the mesh resilient to DHCP changes.

2. **`esp32-fixe-001` now declares `esp32-cam-001` as neighbor** so
   the cam-based discovery can also reach the fixe node.

Nothing else was touched — the code style and structure from the team
is preserved as-is.

---

## Running the 3-device scenario across 2 machines

You said you want to run this:

- **Machine A** (your PC): Docker stack + the badge (flashed and on WiFi)
- **Machine B** (your colleague's PC, or anywhere): the two fixed ESPs

That works out of the box. The only requirement: all 3 ESPs and the
Docker host must be on the **same WiFi / same subnet** so HTTP calls
between them succeed.

Concretely:

1. On machine A, make sure `docker compose --profile dockered-ollama up -d`
   is running. Note your PC's IP on the WiFi.
2. Flash the badge from machine A. In `MqttAdapter.cpp`, set the
   broker IP to machine A's WiFi IP. The badge will publish MQTT to
   your PC.
3. Flash `esp32-fixe-001` and `esp32-cam-001` from machine B. In
   their `MqttAdapter.cpp`, also set the broker IP to machine A's
   WiFi IP (the broker runs on machine A, not machine B).
4. From any machine on the WiFi (but most naturally machine A), run
   `bootstrap_mesh.py` with all three IPs.
5. Run the crew test with the cam as seed:
   ```bash
   docker compose --profile dockered-ollama run --rm crew \
       bash -c 'BADGE_IP=<cam-ip> python -m scripts.test_crew_real_badge'
   ```
   (Rename this script or adapt the intent for a 3-device scenario.)
