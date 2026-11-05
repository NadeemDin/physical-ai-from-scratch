#include <Wire.h>
#include <Adafruit_AHTX0.h>
Adafruit_AHTX0 aht;

void setup() {
  Serial.begin(115200);
#ifdef NEOPIXEL_I2C_POWER
  pinMode(NEOPIXEL_I2C_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_I2C_POWER, HIGH);
#endif
  delay(100);
  Serial.println("--- BOOT ---");
  if (!aht.begin()) Serial.println("AHT20 not found");
}

void loop() {
  sensors_event_t hum, temp;
  aht.getEvent(&hum, &temp);
  Serial.printf("t=%lu ms   Room: %.2f C   Humidity: %.1f %%\r\n", millis(), temp.temperature, hum.relative_humidity);
  delay(1000);
}