void setup() {
  Serial.begin(115200);           // serial link to the Mac
  pinMode(LED_BUILTIN, OUTPUT);   // the small red LED
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.println("Hello from the fan rig");
  delay(500);
  digitalWrite(LED_BUILTIN, LOW);
  delay(500);
}