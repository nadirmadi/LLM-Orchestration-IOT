#include "SoundService.h"

void SoundService::begin(int pin)
{
    _pin = pin;
    Serial.println("[SoundService] Micro prêt sur pin " + String(pin));
}

float SoundService::readDB()
{
    long sum = 0;
    for (int i = 0; i < 50; i++)
    {
        sum += analogRead(_pin);
        delayMicroseconds(200);
    }

    float avg = sum / 50.0;
    float db = 20.0 * log10(avg + 1);

    lastDB = db;
    return db;
}

bool SoundService::hasSignificantChange()
{
    float current = readDB();
    bool changed = abs(current - lastDB) > CHANGE_THRESHOLD;
    lastDB = current;
    return changed;
}