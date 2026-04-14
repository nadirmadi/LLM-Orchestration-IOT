#pragma once
#include <Arduino.h>

class SoundService
{
public:
    void begin(int pin);
    float readDB();
    bool hasSignificantChange();

private:
    int _pin;
    float lastDB = 0.0;
    const float CHANGE_THRESHOLD = 10.0;
};