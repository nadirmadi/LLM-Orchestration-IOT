#pragma once
#include <esp_camera.h>

// AI-Thinker ESP32-CAM pin map
#define CAM_PIN_PWDN 32
#define CAM_PIN_RESET -1
#define CAM_PIN_XCLK 0
#define CAM_PIN_SIOD 26
#define CAM_PIN_SIOC 27
#define CAM_PIN_D7 35
#define CAM_PIN_D6 34
#define CAM_PIN_D5 39
#define CAM_PIN_D4 36
#define CAM_PIN_D3 21
#define CAM_PIN_D2 19
#define CAM_PIN_D1 18
#define CAM_PIN_D0 5
#define CAM_PIN_VSYNC 25
#define CAM_PIN_HREF 23
#define CAM_PIN_PCLK 22

class CameraService {
 public:
  bool begin(framesize_t resolution = FRAMESIZE_QVGA);
  bool isAvailable();
  camera_fb_t* captureFrame();  // caller must call esp_camera_fb_return()

 private:
  bool _initialized = false;
};
