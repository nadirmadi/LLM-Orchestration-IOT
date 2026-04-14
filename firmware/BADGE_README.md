# Badge patient — firmware

Patient badge firmware for the LLMThings v2 project. Exposes the badge
as an HTTP + MQTT device so it can be discovered and managed by the
CrewAI agents via the MCP server.

## What is in here

```
badge_firmware/
├── badge-patient.ino     # entry point (unchanged from the original)
├── AccelService.h/.cpp   # MPU6050 accelerometer (unchanged)
├── SoundService.h/.cpp   # analog microphone (unchanged)
├── MqttAdapter.h/.cpp    # publishes badge/001/* topics (unchanged)
└── HttpAdapter.h/.cpp    # HTTP REST endpoints (MODIFIED for MCP)
```

## What changed from the original code

Only `HttpAdapter.h` and `HttpAdapter.cpp` were modified. Every other
file is byte-for-byte identical to the original version.

### 1. `/capabilities` — new canonical shape

The old format (dict of endpoint paths) has been replaced by the shape
the MCP server's `monitoring_discover_network` tool expects:

```json
{
  "device_id": "badge-001",
  "ip": "192.168.1.50",
  "status": "active",
  "device_type": "badge",
  "location": { "zone": "on_patient", "x": 0.0, "y": 0.0, "z": 1.1 },
  "services": [
    { "name": "imu",   "protocol": "MQTT",
      "details": { "fall_detection": true,
                   "topic": "badge/001/accelerometer" } },
    { "name": "sound", "protocol": "MQTT",
      "details": { "topic": "badge/001/sound" } }
  ],
  "neighbors": []
}
```

Key points:
- service names use the canonical vocabulary (`imu`, `sound`) that the
  CrewAI agents are trained on — NOT `/accelerometer` or `/sound`
- `zone` is hardcoded to `"on_patient"` because the badge is mobile;
  real localization is done by the fixed PIRs, not by the badge itself
- `neighbors` is empty because the badge has no fixed neighbors

### 2. Three new endpoints for MCP compatibility

The Orchestration Agent can now call these, even though they are no-ops
on the badge (the badge is always active by design):

- `POST /wake`            → returns `{"ok": true, "new_status": "active"}`
- `POST /sleep`           → returns `{"ok": true, "new_status": "active"}`
- `POST /activate_service` → acknowledges any service activation request

These exist only so that the agents never crash when they accidentally
treat the badge like a regular fixed sensor.

### 3. `/health`, `/accelerometer`, `/sound` — unchanged semantics

These still work exactly like before — only the raw JSON output is
slightly re-formatted in `HttpAdapter.cpp`. The `AccelService` and
`SoundService` classes were not touched.

## Flashing

Open `badge-patient.ino` in the Arduino IDE (or PlatformIO), set your
WiFi credentials at the top of the `.ino` file, select the ESP32 board,
and upload. Then check the serial monitor for:

```
[WiFi] Connecte — IP : 192.168.x.x
[HTTP] Serveur demarre (MCP-compatible)
[HTTP] IP: http://192.168.x.x
[MQTT] Connexion... OK
```

## Validating the badge from a laptop

Once the badge is on the WiFi, you can hit it directly:

```bash
curl http://<badge-ip>/capabilities
curl http://<badge-ip>/health
curl http://<badge-ip>/accelerometer
curl http://<badge-ip>/sound
```

The `/capabilities` output should exactly match the canonical shape
shown above. If it does, the MCP server's `monitoring_discover_network`
tool can now discover the badge automatically using its IP as the seed.
