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

#include "driver/pulse_cnt.h"
const int PWM_PIN  = 27;   // fan pin 4
const int TACH_PIN = 33;   // fan pin 3 (10k pull-up to 3V)
int duty = 40;             // percent

// Count tach pulses in hardware, ignoring electrical spikes shorter than 10 microseconds
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
  pcnt_channel_set_edge_action(chan, PCNT_CHANNEL_EDGE_ACTION_HOLD, PCNT_CHANNEL_EDGE_ACTION_INCREASE);  // count falling edges
  pcnt_unit_enable(tachUnit);
  pcnt_unit_clear_count(tachUnit);
  pcnt_unit_start(tachUnit);
}
int takePulses() {                       // pulses since last call
  int c = 0;
  pcnt_unit_get_count(tachUnit, &c);
  pcnt_unit_clear_count(tachUnit);
  return c;
}

void setup() {
  Serial.begin(115200);
  statusBegin();
  ledcAttach(PWM_PIN, 25000, 8);              // 25 kHz PWM, 0-255
  ledcWrite(PWM_PIN, duty * 255 / 100);
  tachBegin();
}

String typed = "";

void readSpeed() {                      // type a number 0-100, then Enter
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (typed.length() > 0) {
        duty = constrain(typed.toInt(), 0, 100);
        ledcWrite(PWM_PIN, duty * 255 / 100);
        Serial.printf("\r\n>> duty set to %d%%\r\n", duty);
        typed = "";
      }
    } else if (isDigit(c)) {
      typed += c;
      Serial.print(c);                  // echo so you can see what you type
    }
  }
}

void loop() {
  heartbeat();
  readSpeed();
  int p = takePulses();
  Serial.printf("Duty %d%%   RPM %d\r\n", duty, p * 30);   // 2 pulses per turn
  delay(1000);
}
