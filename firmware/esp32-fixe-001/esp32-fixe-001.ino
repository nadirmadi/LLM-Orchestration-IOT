#include <WiFi.h>
#include "UltrasonicService.h"
#include "HttpAdapter.h"
#include "MqttAdapter.h"

static const char* SSID = "Androidc";
static const char* PASSWORD = "celine2005";

static const int TRIG_PIN = 12;
static const int ECHO_PIN = 14;

UltrasonicService ultrasonic;

void setup() {
    Serial.begin(115200);
    Serial.println("\n=== ESP32 Fixed Node — ultrasonic ===");

    WiFi.begin(SSID, PASSWORD);
    Serial.print("[WiFi] Connecting");
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.println("\n[WiFi] Connected — IP: " + WiFi.localIP().toString());

    ultrasonic.begin(TRIG_PIN, ECHO_PIN);
    setupMqtt();
    setupHttp();

    Serial.println("=== Boot OK — status: light_sleep ===\n");
}

void loop() {
    loopMqtt();
    loopHttp();
}
