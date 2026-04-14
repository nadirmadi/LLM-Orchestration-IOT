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
  // Mesh neighbors — EDIT THESE IPs TO MATCH YOUR DEPLOYMENT
  json += "\"neighbors\":[";
  json += "{\"device_id\":\"esp32-cam-001\","
          "\"ip\":\"192.168.1.52\"},";
  json += "{\"device_id\":\"badge-001\","
          "\"ip\":\"192.168.1.50\"}";
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

void setupHttp() {
  server.on("/capabilities", HTTP_GET, handleCapabilities);
  server.on("/health", HTTP_GET, handleHealth);
  server.on("/ultrasonic", HTTP_GET, handleUltrasonic);
  server.on("/wake", HTTP_POST, handleWake);
  server.on("/sleep", HTTP_POST, handleSleep);
  server.on("/activate_service", HTTP_POST, handleActivateService);

  server.begin();
  Serial.println("[HTTP] Ultrasonic node ready (MCP-compatible)");
  Serial.println("[HTTP] http://" + ipString());
}

void loopHttp() { server.handleClient(); }
