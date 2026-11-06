// Join the Wi-Fi and report the connection.
// Status light: RED 2s = started, GREEN/BLUE = connected, AMBER/BLUE = not connected.
#include <WiFi.h>
#include <Adafruit_NeoPixel.h>
#include "secrets.h"

Adafruit_NeoPixel pixel(1, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);
bool statusOk = false;

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

void heartbeat() {   // call once per loop
  static bool flip = false;
  flip = !flip;
  uint32_t c = statusOk ? pixel.Color(0, 255, 0) : pixel.Color(255, 140, 0);
  pixel.setPixelColor(0, flip ? c : pixel.Color(0, 0, 255));
  pixel.show();
}

void connectWiFi() {
  Serial.print("Connecting to ");
  Serial.print(WIFI_SSID);
  WiFi.mode(WIFI_STA);                      // "station": join a network, don't create one
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    Serial.print(".");
    heartbeat();
    delay(500);
  }
  Serial.print("\r\n");
}

void setup() {
  Serial.begin(115200);
  statusBegin();
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {      // dropped or never joined: keep trying
    statusOk = false;
    Serial.print("Not connected, retrying...\r\n");
    connectWiFi();
  } else {
    statusOk = true;
    Serial.print("Connected. ESP32 address: ");
    Serial.print(WiFi.localIP());
    Serial.print("   signal: ");
    Serial.print(WiFi.RSSI());
    Serial.print(" dBm\r\n");
  }
  heartbeat();
  delay(1000);
}