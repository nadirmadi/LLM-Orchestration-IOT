#include "AccelService.h"

void AccelService::begin()
{
    Wire.begin(8,9);
    mpu.initialize();
    initialized = mpu.testConnection();

    if (!initialized)
    {
        Serial.println("[AccelService] ERREUR : MPU6050 non détecté");
    }
    else
    {
        Serial.println("[AccelService] MPU6050 OK");
        mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);
    }
}

AccelData AccelService::read()
{
    AccelData data;
    int16_t ax, ay, az;

    mpu.getAcceleration(&ax, &ay, &az);

    data.x = ax / 16384.0;
    data.y = ay / 16384.0;
    data.z = az / 16384.0;

    data.norm = sqrt(data.x * data.x +
                     data.y * data.y +
                     data.z * data.z);

    return data;
}

bool AccelService::isAvailable()
{
    return initialized;
}