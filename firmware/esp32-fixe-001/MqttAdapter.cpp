#include "MqttAdapter.h"
#include <PubSubClient.h>
#include <WiFi.h>
#include "UltrasonicService.h"

extern UltrasonicService ultrasonic;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

static const char* BROKER_IP = "10.45.20.119";  // same as badge
static const int BROKER_PORT = 1883;
static const char* DEVICE_ID = "esp32-fixe-001";
static const char* TOPIC = "sensors/esp32-fixe-001/ultrasonic";

static constexpr unsigned long PUBLISH_INTERVAL_MS = 500;

static void reconnectMqtt() {
  while (!mqtt.connected()) {
    Serial.print("[MQTT] Connecting...");
    if (mqtt.connect(DEVICE_ID)) {
      Serial.println(" OK ✅");
      String ip = WiFi.localIP().toString();
      String payload = "{\"status\":\"active\",\"device\":\"" +
                       String(DEVICE_ID) + "\",\"ip\":\"" + ip + "\"}";
      mqtt.publish((String("nodes/") + DEVICE_ID + "/status").c_str(),
                   payload.c_str(), true);
    } else {
      Serial.println(" failed rc=" + String(mqtt.state()));
      delay(3000);
    }
  }
}

void setupMqtt() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[MQTT] WiFi not ready, skipping");
    return;
  }
  mqtt.setServer(BROKER_IP, BROKER_PORT);
  reconnectMqtt();
}

void loopMqtt() {
  if (!mqtt.connected()) reconnectMqtt();
  mqtt.loop();

  static unsigned long lastPublish = 0;
  unsigned long now = millis();

  if (now - lastPublish >= PUBLISH_INTERVAL_MS) {
    float cm = ultrasonic.readCm();
    String payload = "{\"distance_cm\":" + String(cm, 2) + "}";
    mqtt.publish(TOPIC, payload.c_str());
    lastPublish = now;
  }
}
