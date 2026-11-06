// Join Wi-Fi, connect to the MQTT broker, announce "online", send "hello" every second.
// Status light: RED 2s = started, GREEN/BLUE = Wi-Fi + broker OK, AMBER/BLUE = something not connected.
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_NeoPixel.h>
#include "secrets.h"

const char* CLIENT_ID    = "fan1";
const char* TOPIC_STATUS = "rig/fan1/status";
const char* TOPIC_HELLO  = "rig/fan1/hello";

WiFiClient   net;             // the network connection
PubSubClient mqtt(net);       // MQTT, running over that connection

Adafruit_NeoPixel pixel(1, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);
bool statusOk = false;

void statusBegin() {
#ifdef NEOPIXEL_I2C_POWER
  pinMode(NEOPIXEL_I2C_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_I2C_POWER, HIGH);
#endif
  pixel.begin();
  pixel.setBrightness(30);
  pixel.setPixelColor(0, pixel.Color(255, 0, 0));   // RED = just started
  pixel.show();
  delay(2000);
}

void heartbeat() {
  static bool flip = false;
  flip = !flip;
  uint32_t c = statusOk ? pixel.Color(0, 255, 0) : pixel.Color(255, 140, 0);
  pixel.setPixelColor(0, flip ? c : pixel.Color(0, 0, 255));
  pixel.show();
}

void connectWiFi() {
  Serial.print("Wi-Fi: connecting to ");
  Serial.print(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    Serial.print(".");
    delay(500);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("\r\nWi-Fi: connected as ");
    Serial.print(WiFi.localIP());
    Serial.print("\r\n");
  } else {
    Serial.print("\r\nWi-Fi: failed, will retry\r\n");
  }
}

bool connectMQTT() {
  Serial.print("MQTT: connecting to ");
  Serial.print(MQTT_HOST);
  Serial.print(":");
  Serial.print(MQTT_PORT);
  Serial.print(" ... ");
  // Last will: if we vanish without saying goodbye, the broker publishes "offline" (retained) for us.
  bool ok = mqtt.connect(CLIENT_ID, TOPIC_STATUS, 1, true, "offline");
  if (ok) {
    Serial.print("connected\r\n");
    mqtt.publish(TOPIC_STATUS, "online", true);   // true = retained
  } else {
    Serial.print("failed, state ");
    Serial.print(mqtt.state());                   // a code explaining why; see the build log
    Serial.print("\r\n");
  }
  return ok;
}

void setup() {
  Serial.begin(115200);
  statusBegin();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  connectWiFi();
}

void loop() {
  static unsigned long lastTry = 0, lastHello = 0;
  static unsigned long count = 0;

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  } else if (!mqtt.connected() && millis() - lastTry > 5000) {
    lastTry = millis();                            // retry the broker every 5 s, without freezing
    connectMQTT();
  }

  mqtt.loop();                                     // lets the library do its housekeeping

  if (mqtt.connected() && millis() - lastHello >= 1000) {
    lastHello = millis();
    char msg[40];
    snprintf(msg, sizeof(msg), "hello %lu", count++);
    mqtt.publish(TOPIC_HELLO, msg);
    Serial.print("sent: ");
    Serial.print(msg);
    Serial.print("\r\n");
  }

  statusOk = (WiFi.status() == WL_CONNECTED) && mqtt.connected();
  static unsigned long lastBeat = 0;
  if (millis() - lastBeat >= 500) { lastBeat = millis(); heartbeat(); }
}