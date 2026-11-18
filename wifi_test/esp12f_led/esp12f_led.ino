#include <ESP8266WiFi.h>

#define LED_PIN 16  // GPIO16 connectat al LED de l'ESP-12F

void flashLED(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, LOW);   // Encén el LED (actiu en LOW)
    delay(100);
    digitalWrite(LED_PIN, HIGH);  // Apaga el LED
    delay(100);
  }
}

void doScan() {
  // Indiquem visualment que comença l'escaneig mantenint el LED encès o fent un parpelleig
  digitalWrite(LED_PIN, LOW); 
  
  int n = WiFi.scanNetworks(false, true);  // inclou xarxes ocultes
  
  digitalWrite(LED_PIN, HIGH); // Apaguem un cop acabat l'escaneig ràpid

  Serial.printf("N|%d\n", n < 0 ? 0 : n);
  for (int i = 0; i < n; i++) {
    String ssid = WiFi.SSID(i);
    ssid.replace("\n", " ");
    ssid.replace("\r", " ");
    // R|rssi|channel|enc|bssid|ssid
    Serial.printf("R|%d|%d|%d|%s|%s\n",
                  WiFi.RSSI(i), WiFi.channel(i), (int)WiFi.encryptionType(i),
                  WiFi.BSSIDstr(i).c_str(), ssid.c_str());
  }
  Serial.println("END");
  WiFi.scanDelete();
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH); // Estat inicial apagat

  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  // 5 flashos ràpids a l'arrencada per confirmar funcionament
  flashLED(5);

  Serial.println("READY");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "SCAN") {
      doScan();
    }
    else if (cmd == "PING") {
      // Petit flash de confirmació al respondre PING
      digitalWrite(LED_PIN, LOW);
      Serial.println("PONG");
      delay(50);
      digitalWrite(LED_PIN, HIGH);
    }
  }
}