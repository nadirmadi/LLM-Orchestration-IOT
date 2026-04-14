#pragma once

class UltrasonicService {
public:
    void  begin(int trigPin, int echoPin);
    float readCm();
    bool  isAvailable();
    bool  hasSignificantChange();

private:
    int   _trigPin;
    int   _echoPin;
    bool  _initialized        = false;
    float _lastValue          = -1.0f;

    static constexpr float CHANGE_THRESHOLD_CM = 5.0f;
    static constexpr float MAX_RANGE_CM        = 400.0f;
    static constexpr float TIMEOUT_US          = 30000.0f;
};