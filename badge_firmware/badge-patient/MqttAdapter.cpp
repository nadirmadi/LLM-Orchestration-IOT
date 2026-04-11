#include "MqttAdapter.h"
#include <PubSubClient.h>
#include <WiFi.h>
#include "AccelService.h"
#include "SoundService.h"

extern AccelService accel;
extern SoundService sound;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

const char *BROKER_IP = "192.168.89.25";
const int BROKER_PORT = 1883;
const char *DEVICE_ID = "badge-001";

void reconnectMqtt() {
  Serial.println("[MQTT] Tentative de connexion au broker " + String(BROKER_IP) + ":" + String(BROKER_PORT));

  while (!mqtt.connected()) {
    Serial.print("[MQTT] Connexion...");
    if (mqtt.connect(DEVICE_ID)) {
      Serial.println(" OK ✅");
      // Annonce que le badge est en ligne
     String ip = WiFi.localIP().toString();
    String payload = "{\"status\":\"active\","
                 "\"device\":\"badge-001\","
                 "\"ip\":\"" + ip + "\"}";
mqtt.publish("badge/001/status", payload.c_str(), true);
    } else {
      int state = mqtt.state();
      Serial.print(" Échec, code=");
      Serial.println(state);

      switch (state) {
        case -1: Serial.println("Erreur : Pas de connexion réseau"); break;
        case -2: Serial.println("Erreur : Impossible d’établir une connexion TCP au broker"); break;
        case -3: Serial.println("Erreur : Nom du client invalide"); break;
        case -4: Serial.println("Erreur : Connexion au broker refusée"); break;
        case -5: Serial.println("Erreur : Broker non autorisé (authentification ?)"); break;
        case -6: Serial.println("Erreur : Broker non autorisé (certificat TLS ?)"); break;
        default: Serial.println("Erreur inconnue"); break;
      }

      Serial.println("Nouvelle tentative dans 3 secondes...");
      delay(3000);
    }
  }
}


void setupMqtt()
{
    if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[MQTT] ⚠️ WiFi non connecté, impossible de démarrer MQTT");
    return;
  }

  mqtt.setServer(BROKER_IP, BROKER_PORT);
  reconnectMqtt();

}

void loopMqtt()
{
  if (!mqtt.connected())
    reconnectMqtt();
  mqtt.loop();

  unsigned long now = millis();
  static unsigned long lastAccel = 0;
  static unsigned long lastSound = 0;

  if (now - lastAccel >= 20)
  {
    AccelData d = accel.read();
    String payload = "{\"x\":" + String(d.x, 3) +
                     ",\"y\":" + String(d.y, 3) +
                     ",\"z\":" + String(d.z, 3) +
                     ",\"norm\":" + String(d.norm, 3) + "}";
    mqtt.publish("badge/001/accelerometer", payload.c_str());
    lastAccel = now;
  }

  if (now - lastSound >= 200)
{
    float db = sound.readDB();
    String payload = "{\"db\":" + String(db, 1) + "}";
    mqtt.publish("badge/001/sound", payload.c_str());
    lastSound = now;
}
}