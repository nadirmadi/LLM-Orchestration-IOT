// HttpAdapter.cpp — ESP32-CAM node
// Camera-only node: exposes /camera (snapshot) and /camera/stream (MJPEG)
// alongside the standard MCP contract endpoints.

#include "HttpAdapter.h"
#include <WebServer.h>
#include <WiFi.h>
#include <esp_camera.h>
#include "CameraService.h"

extern CameraService camera;

static const char* DEVICE_ID = "esp32-cam-001";
static const char* ZONE = "corridor";
static const float POS_X = 5.0f;
static const float POS_Y = 1.0f;
static const float POS_Z = 2.5f;  // mounted high

// Declared neighbors (by ID). IPs are filled at runtime via
// POST /set_neighbor — they cannot be known at compile time.
#define MAX_NEIGHBORS 4
static const char* NEIGHBOR_IDS[MAX_NEIGHBORS] = {
    "esp32-fixe-001",
    "badge-001",
    nullptr, nullptr
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
  json += "{\"name\":\"camera\",\"protocol\":\"HTTP\",";
  json += "\"details\":{\"stream\":true,";
  json += "\"snapshot_endpoint\":\"/camera\",";
  json += "\"stream_endpoint\":\"/camera/stream\",";
  json += "\"resolution\":\"QVGA\",\"fov\":120}}";
  json += "],";
  json += "],";
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
  String json = "{\"status\":\"" + deviceStatus + "\","
                "\"device\":\"" +
                String(DEVICE_ID) + "\","
                "\"rssi\":" +
                String(WiFi.RSSI()) + "}";
  server.send(200, "application/json", json);
}

static void handleSnapshot() {
    if (!camera.isAvailable()) {
        server.send(503, "application/json",
                    "{\"error\":\"camera not available\"}");
        return;
    }
    camera_fb_t* fb = camera.captureFrame();
    if (!fb) {
        server.send(500, "application/json",
                    "{\"error\":\"frame capture failed\"}");
        return;
    }

    // send raw JPEG bytes
    WiFiClient client = server.client();
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: image/jpeg");
    client.print("Content-Length: ");
    client.println(fb->len);
    client.println("Content-Disposition: inline; filename=snapshot.jpg");
    client.println();
    client.write(fb->buf, fb->len);

    esp_camera_fb_return(fb);
}

static void handleStream() {
  if (!camera.isAvailable()) {
    server.send(503, "application/json",
                "{\"error\":\"camera not available\"}");
    return;
  }

  WiFiClient client = server.client();
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  client.println("Connection: keep-alive");
  client.println();

  while (client.connected()) {
    camera_fb_t* fb = camera.captureFrame();
    if (!fb) break;

    client.println("--frame");
    client.println("Content-Type: image/jpeg");
    client.print("Content-Length: ");
    client.println(fb->len);
    client.println();
    client.write(fb->buf, fb->len);
    client.println();

    esp_camera_fb_return(fb);
    delay(33);  // ~30 fps
  }
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

  if (requested != "camera") {
    server.send(400, "application/json",
                "{\"ok\":false,\"error\":\"unknown service\","
                "\"available_services\":[\"camera\"]}");
    return;
  }

  String json = "{\"ok\":true,\"service\":\"camera\","
                "\"status\":\"" +
                deviceStatus + "\","
                "\"stream_url\":\"http://" +
                ipString() + "/camera/stream\"}";
  server.send(200, "application/json", json);
}

// POST /set_neighbor — teach this device a neighbor's runtime IP.
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
  server.on("/camera", HTTP_GET, handleSnapshot);
  server.on("/camera/stream", HTTP_GET, handleStream);
  server.on("/wake", HTTP_POST, handleWake);
  server.on("/sleep", HTTP_POST, handleSleep);
  server.on("/activate_service", HTTP_POST, handleActivateService);
  server.on("/set_neighbor", HTTP_POST, handleSetNeighbor);

  server.begin();
  Serial.println("[HTTP] Camera node ready (MCP-compatible)");
  Serial.println("[HTTP] http://" + ipString());
}

void loopHttp() { server.handleClient(); }
