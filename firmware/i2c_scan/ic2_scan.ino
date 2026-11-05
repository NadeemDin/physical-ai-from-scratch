#include <Wire.h>
// ---- Status light: RED for 2 s = just started, then GREEN/BLUE = running fine,
// ---- AMBER/BLUE = running but something is missing. RED again = it restarted.
#include <Adafruit_NeoPixel.h>
Adafruit_NeoPixel pixel(1, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);
bool statusOk = true;

void statusBegin() {
#ifdef NEOPIXEL_I2C_POWER
  pinMode(NEOPIXEL_I2C_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_I2C_POWER, HIGH);   // powers the NeoPixel and the STEMMA QT port
#endif
  pixel.begin();
  pixel.setBrightness(30);
  pixel.setPixelColor(0, pixel.Color(255, 0, 0));   // RED = just started
  pixel.show();
  delay(2000);
}

void heartbeat() {                                  // call once per loop
  static bool flip = false;
  flip = !flip;
  uint32_t c = statusOk ? pixel.Color(0, 255, 0) : pixel.Color(255, 140, 0);
  pixel.setPixelColor(0, flip ? c : pixel.Color(0, 0, 255));
  pixel.show();
}
// --------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  statusBegin();
  Wire.begin();
}

void loop() {
  Serial.print("Scanning I2C...\r\n");
  int count = 0;
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) { Serial.printf("  found 0x%02X\r\n", addr); count++; }
  }
  statusOk = (count == 4);          // GREEN/BLUE only when all four sensors answer
  for (int i = 0; i < 3; i++) { heartbeat(); delay(1000); }
}