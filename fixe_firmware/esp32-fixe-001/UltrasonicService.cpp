#include "UltrasonicService.h"
#include <Arduino.h>

void UltrasonicService::begin(int trigPin, int echoPin) {
    _trigPin     = trigPin;
    _echoPin     = echoPin;
    _initialized = true;

    pinMode(_trigPin, OUTPUT);
    pinMode(_echoPin, INPUT);
    digitalWrite(_trigPin, LOW);

    Serial.println("[UltrasonicService] HC-SR04 ready"
                   " trig=" + String(trigPin) +
                   " echo=" + String(echoPin));
}

float UltrasonicService::readCm() {
    if (!_initialized) return -1.0f;

    digitalWrite(_trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(_trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(_trigPin, LOW);

    long duration = pulseIn(_echoPin, HIGH, (unsigned long)TIMEOUT_US);
    if (duration == 0) return MAX_RANGE_CM;

    float cm   = (duration * 0.0343f) / 2.0f;
    _lastValue = cm;
    return cm;
}

bool UltrasonicService::isAvailable() { return _initialized; }

bool UltrasonicService::hasSignificantChange() {
    float current = readCm();
    bool  changed = abs(current - _lastValue) > CHANGE_THRESHOLD_CM;
    _lastValue    = current;
    return changed;
}