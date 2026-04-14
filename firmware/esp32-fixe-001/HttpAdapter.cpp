// HttpAdapter.cpp — ultrasonic node
// MCP contract: same endpoints as the badge (/capabilities, /health,
// /wake, /sleep, /activate_service) + /ultrasonic for on-demand reads.

#include "HttpAdapter.h"
#include <WebServer.h>
#include <WiFi.h>
#include "UltrasonicService.h"

extern UltrasonicService ultrasonic;

// ── Edit these per physical deployment ───────────────────────────
static const char* DEVICE_ID = "esp32-fixe-001";
static const char* ZONE = "corridor";
static const float POS_X = 4.0f;
static const float POS_Y = 1.0f;
static const float POS_Z = 0.5f;

// Declare which devices are neighbors (by ID). Their IPs are NOT known
// at compile time — they are learned at runtime via POST /set_neighbor
// so that the mesh still works across DHCP changes.
#define MAX_NEIGHBORS 4
static const char* NEIGHBOR_IDS[MAX_NEIGHBORS] = {
    "esp32-cam-001",   // the camera, also in the corridor
    nullptr, nullptr, nullptr
};
static String neighborIps[MAX_NEIGHBORS] = { "", "", "", "" };

static String deviceStatus = "light_sleep";

WebServer server(80);

static String ipString() { return WiFi.localIP().toString(); }

static String buildCapabilitiesJson() {
  String json = "{";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"ip\":\"" + ipString() + "\",";
  json += "\"status\":\"" + deviceStatus + "\",";
  json += "\"device_type\":\"fixed\",";
  json += "\"location\":{";
  json += "\"zone\":\"" + String(ZONE) + "\",";
  json += "\"x\":" + String(POS_X, 2) + ",";
  json += "\"y\":" + String(POS_Y, 2) + ",";
  json += "\"z\":" + String(POS_Z, 2);
  json += "},";
  json += "\"services\":[";
  json += "{\"name\":\"ultrasonic\",\"protocol\":\"HTTP\",";
  json += "\"details\":{\"max_range_cm\":400,";
  json += "\"mqtt_topic\":\"sensors/esp32-fixe-001/ultrasonic\"}}";
  json += "],";
  // Neighbors: only include those whose IP we already know.
  json += "\"neighbors\":[";
  bool first = true;
  for (int i = 0; i < MAX_NEIGHBORS; i++) {
    if (NEIGHBOR_IDS[i] == nullptr) break;
    if (neighborIps[i].length() == 0) continue;
    if (!first) json += ",";
    json += "{\"device_id\":\"" + String(NEIGHBOR_IDS[i]) +
            "\",\"ip\":\"" + neighborIps[i] + "\"}";
    first = false;
  }
  json += "]";
  json += "}";
  return json;
}

static void handleCapabilities() {
  server.send(200, "application/json", buildCapabilitiesJson());
}

static void handleHealth() {
  String json = "{";
  json += "\"status\":\"" + deviceStatus + "\",";
  json += "\"device\":\"" + String(DEVICE_ID) + "\",";
  json += "\"rssi\":" + String(WiFi.RSSI());
  json += "}";
  server.send(200, "application/json", json);
}

static void handleUltrasonic() {
  float cm = ultrasonic.readCm();
  String json = "{\"distance_cm\":" + String(cm, 2) + "}";
  server.send(200, "application/json", json);
}

static void handleWake() {
  deviceStatus = "active";
  server.send(200, "application/json",
               "{\"ok\":true,\"new_status\":\"active\"}");
}

static void handleSleep() {
  deviceStatus = "light_sleep";
  server.send(200, "application/json",
               "{\"ok\":true,\"new_status\":\"light_sleep\"}");
}

static void handleActivateService() {
  String body = server.arg("plain");
  String requested = "unknown";

  int key = body.indexOf("\"service\"");
  if (key >= 0) {
    int colon = body.indexOf(':', key);
    int q1 = body.indexOf('"', colon + 1);
    int q2 = body.indexOf('"', q1 + 1);
    if (q1 >= 0 && q2 > q1) requested = body.substring(q1 + 1, q2);
  }

  if (requested != "ultrasonic") {
    server.send(400, "application/json",
                "{\"ok\":false,\"error\":\"unknown service\","
                "\"available_services\":[\"ultrasonic\"]}");
    return;
  }

  String json = "{\"ok\":true,\"service\":\"" + requested + "\","
                "\"status\":\"" +
                deviceStatus + "\"}";
  server.send(200, "application/json", json);
}

// POST /set_neighbor with body { "device_id": "esp32-cam-001",
//                                 "ip": "192.168.1.42" }
// Lets the orchestration / bootstrap script teach this device the
// runtime IP of a declared neighbor, so mesh discovery can traverse.
static void handleSetNeighbor() {
  String body = server.arg("plain");
  String wantedId = "";
  String wantedIp = "";

  int kId = body.indexOf("\"device_id\"");
  if (kId >= 0) {
    int q1 = body.indexOf('"', body.indexOf(':', kId) + 1);
    int q2 = body.indexOf('"', q1 + 1);
    if (q1 >= 0 && q2 > q1) wantedId = body.substring(q1 + 1, q2);
  }
  int kIp = body.indexOf("\"ip\"");
  if (kIp >= 0) {
    int q1 = body.indexOf('"', body.indexOf(':', kIp) + 1);
    int q2 = body.indexOf('"', q1 + 1);
    if (q1 >= 0 && q2 > q1) wantedIp = body.substring(q1 + 1, q2);
  }

  for (int i = 0; i < MAX_NEIGHBORS; i++) {
    if (NEIGHBOR_IDS[i] == nullptr) break;
    if (String(NEIGHBOR_IDS[i]) == wantedId) {
      neighborIps[i] = wantedIp;
      String json = "{\"ok\":true,\"device_id\":\"" + wantedId +
                    "\",\"ip\":\"" + wantedIp + "\"}";
      server.send(200, "application/json", json);
      return;
    }
  }
  server.send(404, "application/json",
              "{\"ok\":false,\"error\":\"not a declared neighbor\"}");
}

void setupHttp() {
  server.on("/capabilities", HTTP_GET, handleCapabilities);
  server.on("/health", HTTP_GET, handleHealth);
  server.on("/ultrasonic", HTTP_GET, handleUltrasonic);
  server.on("/wake", HTTP_POST, handleWake);
  server.on("/sleep", HTTP_POST, handleSleep);
  server.on("/activate_service", HTTP_POST, handleActivateService);
  server.on("/set_neighbor", HTTP_POST, handleSetNeighbor);

  server.begin();
  Serial.println("[HTTP] Ultrasonic node ready (MCP-compatible)");
  Serial.println("[HTTP] http://" + ipString());
}

void loopHttp() { server.handleClient(); }
