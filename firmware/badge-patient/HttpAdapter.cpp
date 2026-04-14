// ─────────────────────────────────────────────────────────────────
//  HttpAdapter.cpp
//
//  Patient badge HTTP surface, aligned with the LLMThings v2 MCP
//  server contract. The canonical JSON shape for /capabilities must
//  match exactly what the Monitoring Agent expects, because the MCP
//  tool `monitoring_discover_network` parses it and stores it as-is
//  in the SQLite database.
//
//  Endpoints:
//    GET  /capabilities        — canonical device JSON (MCP contract)
//    GET  /health              — status, battery, rssi
//    GET  /accelerometer       — last IMU reading (x, y, z, norm)
//    GET  /sound               — last sound level (dB)
//    POST /wake                — no-op, badge is always active
//    POST /sleep               — no-op, badge is always active
//    POST /activate_service    — no-op, returns { ok, service, status }
// ─────────────────────────────────────────────────────────────────

#include "HttpAdapter.h"
#include <WebServer.h>
#include <WiFi.h>
#include "AccelService.h"
#include "SoundService.h"

extern AccelService accel;
extern SoundService sound;

// ─── Badge identity (hardcoded for the MVP) ──────────────────────
// In a future multi-badge deployment these would go into a config.h
// and be per-device. For now there is only one badge, badge-001.
static const char* DEVICE_ID   = "badge-001";
static const char* DEVICE_TYPE = "badge";
static const char* ZONE        = "on_patient";
static const float POS_X       = 0.0f;
static const float POS_Y       = 0.0f;
static const float POS_Z       = 1.1f;   // ~worn on the chest

WebServer server(80);

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────
static String ipString() {
    return WiFi.localIP().toString();
}

// Build the canonical /capabilities JSON. It must match exactly the
// shape expected by the MCP server's upsert_device() (see
// database/device_registry.py in the Python side).
static String buildCapabilitiesJson() {
    String ip = ipString();

    String json = "{";
    json += "\"device_id\":\"";   json += DEVICE_ID;   json += "\",";
    json += "\"ip\":\"";          json += ip;          json += "\",";
    json += "\"status\":\"active\",";
    json += "\"device_type\":\""; json += DEVICE_TYPE; json += "\",";

    // location
    json += "\"location\":{";
    json += "\"zone\":\"";        json += ZONE;        json += "\",";
    json += "\"x\":";             json += String(POS_X, 2); json += ",";
    json += "\"y\":";             json += String(POS_Y, 2); json += ",";
    json += "\"z\":";             json += String(POS_Z, 2);
    json += "},";

    // services — canonical names (imu, sound) matching the agents' vocabulary
    json += "\"services\":[";
    json += "{\"name\":\"imu\",\"protocol\":\"MQTT\",";
    json +=  "\"details\":{\"fall_detection\":true,"
             "\"topic\":\"badge/001/accelerometer\"}},";
    json += "{\"name\":\"sound\",\"protocol\":\"MQTT\",";
    json +=  "\"details\":{\"topic\":\"badge/001/sound\"}}";
    json += "],";

    // Mesh neighbors — the badge knows its fixed infrastructure peers
    // so discovery can reach the whole deployment from the badge.
    // EDIT THESE IPs TO MATCH YOUR DEPLOYMENT.
    json += "\"neighbors\":[";
    json += "{\"device_id\":\"esp32-cam-001\",";
    json += "\"ip\":\"192.168.135.77\"},";
    json += "{\"device_id\":\"esp32-fixe-001\",";
    json += "\"ip\":\"192.168.135.1\"}";
    json += "]";
    json += "}";

    return json;
}

// ─────────────────────────────────────────────────────────────────
// Route handlers
// ─────────────────────────────────────────────────────────────────
static void handleCapabilities() {
    server.send(200, "application/json", buildCapabilitiesJson());
}

static void handleHealth() {
    String ip = ipString();
    String json = "{";
    json += "\"status\":\"active\",";
    json += "\"device\":\""; json += DEVICE_ID; json += "\",";
    json += "\"battery\":87,";
    json += "\"rssi\":";     json += String(WiFi.RSSI());
    json += "}";
    server.send(200, "application/json", json);
}

static void handleAccelerometer() {
    AccelData d = accel.read();
    String json = "{";
    json += "\"x\":";    json += String(d.x, 3);    json += ",";
    json += "\"y\":";    json += String(d.y, 3);    json += ",";
    json += "\"z\":";    json += String(d.z, 3);    json += ",";
    json += "\"norm\":"; json += String(d.norm, 3);
    json += "}";
    server.send(200, "application/json", json);
}

static void handleSound() {
    float db = sound.readDB();
    String json = "{\"db\":";
    json += String(db, 1);
    json += "}";
    server.send(200, "application/json", json);
}

// The badge is always active. /wake and /sleep are no-ops that keep
// the contract with the Orchestration Agent: whatever it calls, the
// endpoint answers { "ok": true, "status": "active" }.
static void handleWake() {
    server.send(200, "application/json",
                "{\"ok\":true,\"new_status\":\"active\","
                 "\"note\":\"badge is always active\"}");
}

static void handleSleep() {
    server.send(200, "application/json",
                "{\"ok\":true,\"new_status\":\"active\","
                 "\"note\":\"badge cannot be put to sleep\"}");
}

// /activate_service expects a JSON body like { "service": "imu" }.
// The badge does not need to toggle services on and off — everything
// is already streaming on MQTT — so we just acknowledge.
static void handleActivateService() {
    String body = server.arg("plain");
    // Very light parsing: we do not need a full JSON parser for this.
    String requested = "unknown";
    int key = body.indexOf("\"service\"");
    if (key >= 0) {
        int colon = body.indexOf(':', key);
        int q1    = body.indexOf('"', colon + 1);
        int q2    = body.indexOf('"', q1 + 1);
        if (q1 >= 0 && q2 > q1) {
            requested = body.substring(q1 + 1, q2);
        }
    }

    String json = "{";
    json += "\"ok\":true,";
    json += "\"service\":\""; json += requested; json += "\",";
    json += "\"status\":\"active\"";
    json += "}";
    server.send(200, "application/json", json);
}

// ─────────────────────────────────────────────────────────────────
// Setup / loop (called from badge-patient.ino)
// ─────────────────────────────────────────────────────────────────
void setupHttp() {
    server.on("/capabilities",     HTTP_GET,  handleCapabilities);
    server.on("/health",           HTTP_GET,  handleHealth);
    server.on("/accelerometer",    HTTP_GET,  handleAccelerometer);
    server.on("/sound",            HTTP_GET,  handleSound);
    server.on("/wake",             HTTP_POST, handleWake);
    server.on("/sleep",            HTTP_POST, handleSleep);
    server.on("/activate_service", HTTP_POST, handleActivateService);

    server.begin();
    Serial.println("[HTTP] Serveur demarre (MCP-compatible)");
    Serial.print  ("[HTTP] IP: http://");
    Serial.println(WiFi.localIP());
}

void loopHttp() {
    server.handleClient();
}
