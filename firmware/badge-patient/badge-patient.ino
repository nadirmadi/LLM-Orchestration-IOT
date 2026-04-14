#include <WiFi.h>
#include "AccelService.h"
#include "SoundService.h"
#include "HttpAdapter.h"
#include "MqttAdapter.h"
// --- Configuration ---
const char* SSID     = "Nadir";
const char* PASSWORD = "N12345678";
const int   MIC_PIN  = 1;

// --- Instances globales ---
AccelService accel;
SoundService sound;

void setup() {
  Serial.begin(115200);
  Serial.println("\n=== Badge Patient — LLMThings ===");

  // WiFi
  WiFi.begin(SSID, PASSWORD);
  Serial.print("[WiFi] Connexion");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[WiFi] Connecté — IP : " + WiFi.localIP().toString());

  // Services
  accel.begin();
  sound.begin(MIC_PIN);

  // Adapters
  setupMqtt();
  setupHttp();

  Serial.println("=== Démarrage OK ===\n");
}

void loop() {
  loopMqtt();
  loopHttp();
}