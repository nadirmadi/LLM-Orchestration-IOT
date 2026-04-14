#include <WiFi.h>
#include "CameraService.h"
#include "HttpAdapter.h"

static const char* SSID = "Androidc";
static const char* PASSWORD = "celine2005";

CameraService camera;

void setup() {
  Serial.begin(115200);
  Serial.println("\n=== ESP32-CAM Node ===");

  WiFi.begin(SSID, PASSWORD);
  Serial.print("[WiFi] Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[WiFi] Connected — IP: " + WiFi.localIP().toString());

  camera.begin(FRAMESIZE_QVGA);
  setupHttp();

  Serial.println("=== Boot OK — status: light_sleep ===\n");
}

void loop() { loopHttp(); }
