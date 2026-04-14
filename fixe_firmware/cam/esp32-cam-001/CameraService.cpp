#include "CameraService.h"
#include <Arduino.h>

bool CameraService::begin(framesize_t resolution) {
  camera_config_t cfg;
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer = LEDC_TIMER_0;
  cfg.pin_d0 = CAM_PIN_D0;
  cfg.pin_d1 = CAM_PIN_D1;
  cfg.pin_d2 = CAM_PIN_D2;
  cfg.pin_d3 = CAM_PIN_D3;
  cfg.pin_d4 = CAM_PIN_D4;
  cfg.pin_d5 = CAM_PIN_D5;
  cfg.pin_d6 = CAM_PIN_D6;
  cfg.pin_d7 = CAM_PIN_D7;
  cfg.pin_xclk = CAM_PIN_XCLK;
  cfg.pin_pclk = CAM_PIN_PCLK;
  cfg.pin_vsync = CAM_PIN_VSYNC;
  cfg.pin_href = CAM_PIN_HREF;
  cfg.pin_sscb_sda = CAM_PIN_SIOD;
  cfg.pin_sscb_scl = CAM_PIN_SIOC;
  cfg.pin_pwdn = CAM_PIN_PWDN;
  cfg.pin_reset = CAM_PIN_RESET;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.frame_size = resolution;
  cfg.jpeg_quality = 12;
  cfg.fb_count = 2;  // double-buffer for smoother streaming

  if (esp_camera_init(&cfg) != ESP_OK) {
    Serial.println("[CameraService] Init failed");
    _initialized = false;
    return false;
  }
  _initialized = true;
  Serial.println("[CameraService] ESP32-CAM ready");
  return true;
}

bool CameraService::isAvailable() { return _initialized; }

camera_fb_t* CameraService::captureFrame() {
  if (!_initialized) return nullptr;
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) Serial.println("[CameraService] Frame capture failed");
  return fb;
}
