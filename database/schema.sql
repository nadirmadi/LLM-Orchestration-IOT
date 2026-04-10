-- ─────────────────────────────────────────────────────────────────
--  LLMThings — Monitoring database schema
--  Only the Monitoring Agent is allowed to write to these tables.
-- ─────────────────────────────────────────────────────────────────

-- Devices: one row per ESP32 (badge or fixed sensor)
CREATE TABLE IF NOT EXISTS devices (
    device_id              TEXT PRIMARY KEY,
    ip                     TEXT    NOT NULL,
    status                 TEXT    NOT NULL DEFAULT 'unknown',
        -- one of: active, idle, light_sleep, deep_sleep, inactive, unknown
    device_type            TEXT    NOT NULL DEFAULT 'fixed',
        -- one of: fixed (corridor sensor), badge (patient badge)
    zone                   TEXT    NOT NULL DEFAULT 'unknown',
    x                      REAL    NOT NULL DEFAULT 0.0,
    y                      REAL    NOT NULL DEFAULT 0.0,
    z                      REAL    NOT NULL DEFAULT 0.0,
    last_seen              TEXT,
    last_capabilities_pull TEXT
);

-- Services exposed by each device (camera, pir, imu, sound, ...)
-- Stored in a child table so the Orchestration Agent can ask
-- "give me all devices that expose a service named X".
CREATE TABLE IF NOT EXISTS services (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id    TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    protocol     TEXT    NOT NULL,
    details_json TEXT    NOT NULL DEFAULT '{}',
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_services_device_id ON services(device_id);
CREATE INDEX IF NOT EXISTS idx_services_name      ON services(name);

-- Mesh-discovery neighbors graph
CREATE TABLE IF NOT EXISTS neighbors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     TEXT    NOT NULL,
    neighbor_id   TEXT    NOT NULL,
    FOREIGN KEY (device_id)   REFERENCES devices(device_id) ON DELETE CASCADE,
    UNIQUE (device_id, neighbor_id)
);

CREATE INDEX IF NOT EXISTS idx_neighbors_device_id ON neighbors(device_id);
