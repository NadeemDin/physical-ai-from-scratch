// Step 1c-iii: read all sensors and publish one JSON message per second over MQTT.
//
// Topics (fan1 = this rig):
//   rig/fan1/features  out  one JSON message per second with all readings
//   rig/fan1/status    out  "online", or "offline" from the broker if the rig disappears (retained)
//   rig/fan1/cmd       in   a number 0-100 sets the fan duty (%)
//
// Libraries (Library Manager): PubSubClient (Nick O'Leary), Adafruit AHTX0, Adafruit INA219,
// Adafruit TMP117, Adafruit ADXL345, Adafruit NeoPixel.
//
// Status light: RED 2 s = started, GREEN/BLUE = all OK, AMBER/BLUE = Wi-Fi, broker or a sensor missing.

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include <Adafruit_INA219.h>
#include <Adafruit_TMP117.h>
#include <Adafruit_ADXL345_U.h>
#include <Adafruit_NeoPixel.h>
#include "driver/pulse_cnt.h"
#include "secrets.h"

const char* CLIENT_ID      = "fan1";
const char* TOPIC_FEATURES = "rig/fan1/features";
const char* TOPIC_STATUS   = "rig/fan1/status";
const char* TOPIC_CMD      = "rig/fan1/cmd";
const int PWM_PIN = 27, TACH_PIN = 33;

// ---------- Status light ----------
Adafruit_NeoPixel pixel(1, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);
bool sensorsOk = true;
bool statusOk = false;

void statusBegin() {
#ifdef NEOPIXEL_I2C_POWER
  pinMode(NEOPIXEL_I2C_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_I2C_POWER, HIGH);          // powers the NeoPixel and the STEMMA QT port
#endif
  pixel.begin();
  pixel.setBrightness(30);
  pixel.setPixelColor(0, pixel.Color(255, 0, 0));  // RED = just started
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

// ---------- Sensors ----------
Adafruit_AHTX0 aht;
Adafruit_INA219 ina;
Adafruit_TMP117 tmp;
Adafruit_ADXL345_Unified adxl(12345);

// ---------- Tach: hardware pulse counter, ignores spikes shorter than 10 microseconds ----------
pcnt_unit_handle_t tachUnit = NULL;

void tachBegin() {
  pcnt_unit_config_t unitCfg = {};
  unitCfg.low_limit = -32768;
  unitCfg.high_limit = 32767;
  pcnt_new_unit(&unitCfg, &tachUnit);
  pcnt_glitch_filter_config_t filterCfg = {};
  filterCfg.max_glitch_ns = 10000;
  pcnt_unit_set_glitch_filter(tachUnit, &filterCfg);
  pcnt_chan_config_t chanCfg = {};
  chanCfg.edge_gpio_num = TACH_PIN;
  chanCfg.level_gpio_num = -1;
  pcnt_channel_handle_t chan = NULL;
  pcnt_new_channel(tachUnit, &chanCfg, &chan);
  pcnt_channel_set_edge_action(chan, PCNT_CHANNEL_EDGE_ACTION_HOLD, PCNT_CHANNEL_EDGE_ACTION_INCREASE);
  pcnt_unit_enable(tachUnit);
  pcnt_unit_clear_count(tachUnit);
  pcnt_unit_start(tachUnit);
}

int takePulses() {                                  // pulses since the last call
  int c = 0;
  pcnt_unit_get_count(tachUnit, &c);
  pcnt_unit_clear_count(tachUnit);
  return c;
}

// ---------- Fan speed ----------
int duty = 40;

void setDuty(int d) {
  duty = constrain(d, 0, 100);
  ledcWrite(PWM_PIN, duty * 255 / 100);
}

// ---------- One-second window: vibration at ~400/s, current at ~100/s ----------
double sx, sy, sz, sxx, syy, szz;                  // vibration sums
float minA[3], maxA[3];
int nVib = 0;
double sumMa = 0, sumV = 0;                        // current + voltage sums
int nPow = 0;

void resetWindow() {
  sx = sy = sz = sxx = syy = szz = 0;
  nVib = 0;
  for (int i = 0; i < 3; i++) { minA[i] = 1e9; maxA[i] = -1e9; }
  sumMa = sumV = 0;
  nPow = 0;
}

void sampleVibration() {
  sensors_event_t a;
  adxl.getEvent(&a);
  float v[3] = { a.acceleration.x, a.acceleration.y, a.acceleration.z };
  sx += v[0];  sy += v[1];  sz += v[2];
  sxx += v[0] * v[0];  syy += v[1] * v[1];  szz += v[2] * v[2];
  for (int i = 0; i < 3; i++) {
    minA[i] = min(minA[i], v[i]);
    maxA[i] = max(maxA[i], v[i]);
  }
  nVib++;
}

void samplePower() {
  sumMa += ina.getCurrent_mA();
  sumV  += ina.getBusVoltage_V();
  nPow++;
}

// RMS of the vibration only: the steady part (gravity) is removed first
float rmsAC(double s, double ss) {
  if (nVib < 2) return 0;
  double mean = s / nVib;
  double var = ss / nVib - mean * mean;
  return var > 0 ? sqrt(var) : 0;
}

// ---------- Wi-Fi + MQTT ----------
WiFiClient net;
PubSubClient mqtt(net);

void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  char buf[8] = {0};
  memcpy(buf, payload, min(len, (unsigned int)7));
  setDuty(atoi(buf));
  Serial.printf(">> duty set to %d%% via MQTT\r\n", duty);
}

void connectWiFi() {
  Serial.printf("Wi-Fi: connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // no Wi-Fi power saving: commands arrive without delay
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    Serial.print(".");
    delay(500);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\r\nWi-Fi: connected as %s\r\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.print("\r\nWi-Fi: failed, will retry\r\n");
  }
}

void connectMQTT() {
  Serial.printf("MQTT: connecting to %s:%d ... ", MQTT_HOST, MQTT_PORT);
  if (mqtt.connect(CLIENT_ID, TOPIC_STATUS, 1, true, "offline")) {   // last will: "offline", retained
    mqtt.publish(TOPIC_STATUS, "online", true);
    mqtt.subscribe(TOPIC_CMD, 1);
    Serial.print("connected\r\n");
  } else {
    Serial.printf("failed, state %d\r\n", mqtt.state());
  }
}

// ---------- Optional: type a duty in screen (0-100, then Enter) ----------
String typed = "";

void readSerialDuty() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (typed.length() > 0) {
        setDuty(typed.toInt());
        Serial.printf("\r\n>> duty set to %d%%\r\n", duty);
        typed = "";
      }
    } else if (isDigit(c)) {
      typed += c;
      Serial.print(c);
    }
  }
}

// ---------- Setup + loop ----------
uint32_t lastPublish = 0, lastVibUs = 0, lastPowUs = 0, lastMqttTry = 0;

void setup() {
  Serial.begin(115200);
  statusBegin();

  Wire.setClock(400000);                            // faster I2C, needed for 400 vibration readings a second
  if (!aht.begin())  { Serial.print("AHT20 missing\r\n");   sensorsOk = false; }
  if (!ina.begin())  { Serial.print("INA219 missing\r\n");  sensorsOk = false; }
  if (!tmp.begin())  { Serial.print("TMP117 missing\r\n");  sensorsOk = false; }
  if (!adxl.begin()) { Serial.print("ADXL345 missing\r\n"); sensorsOk = false; }
  adxl.setRange(ADXL345_RANGE_4_G);
  adxl.setDataRate(ADXL345_DATARATE_800_HZ);

  ledcAttach(PWM_PIN, 25000, 8);
  setDuty(duty);
  tachBegin();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(512);
  connectWiFi();

  resetWindow();
  takePulses();
  lastPublish = millis();
}

void loop() {
  // 1. Keep the connections up, without stopping the measurements for long
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  } else if (!mqtt.connected() && millis() - lastMqttTry > 5000) {
    lastMqttTry = millis();
    connectMQTT();
  }
  mqtt.loop();
  readSerialDuty();

  // 2. Fast sampling
  uint32_t nowUs = micros();
  if (nowUs - lastVibUs >= 2500)  { lastVibUs = nowUs; sampleVibration(); }   // ~400 per second
  if (nowUs - lastPowUs >= 10000) { lastPowUs = nowUs; samplePower(); }       // ~100 per second

  // 3. Once a second: summarise and publish
  uint32_t now = millis();
  if (now - lastPublish >= 1000) {
    uint32_t elapsed = now - lastPublish;
    lastPublish = now;

    int rpm = (int)(takePulses() * 30000UL / elapsed);    // 2 pulses per turn, scaled to real time
    sensors_event_t hum, air, hub;
    aht.getEvent(&hum, &air);
    tmp.getEvent(&hub);

    float peak = 0;                                        // largest swing on any axis, centre to edge
    for (int i = 0; i < 3; i++) peak = max(peak, (maxA[i] - minA[i]) / 2);

    char json[400];
    snprintf(json, sizeof(json),
      "{\"uptime_ms\":%lu,\"duty\":%d,\"rpm\":%d,\"current_ma\":%.1f,\"bus_v\":%.2f,"
      "\"hub_c\":%.2f,\"airflow_c\":%.2f,\"rh\":%.1f,"
      "\"ax_rms\":%.4f,\"ay_rms\":%.4f,\"az_rms\":%.4f,\"a_peak\":%.4f,"
      "\"vib_samples\":%d,\"power_samples\":%d}",
      (unsigned long)now, duty, rpm,
      nPow ? sumMa / nPow : 0.0, nPow ? sumV / nPow : 0.0,
      hub.temperature, air.temperature, hum.relative_humidity,
      rmsAC(sx, sxx), rmsAC(sy, syy), rmsAC(sz, szz), peak,
      nVib, nPow);

    if (mqtt.connected()) mqtt.publish(TOPIC_FEATURES, json);
    Serial.print(json);
    Serial.print("\r\n");

    statusOk = sensorsOk && WiFi.status() == WL_CONNECTED && mqtt.connected();
    heartbeat();
    resetWindow();
  }
}
