#pragma once
#include <Wire.h>
#include <MPU6050.h>

struct AccelData
{
    float x, y, z;
    float norm;
};

class AccelService
{
public:
    void begin();
    AccelData read();
    bool isAvailable();

private:
    MPU6050 mpu;
    bool initialized = false;
};