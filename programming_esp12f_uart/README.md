# HackBat ESP-12F WiFi Scanner & UART Bridge

Aquest projecte implementa un escàner de xarxes Wi-Fi portàtil utilitzant una **HackBat**, on l'**RP2040** gestiona la interfície gràfica (pantalla OLED SH1106 i botons de navegació) i actua com a pont UART cap a un mòdul **ESP-12F**, encarregat de realitzar l'escaneig de xarxes en segon pla.

Per programar l'**ESP-12F** un cop soldat a la placa de **HackBat**, s'ha de fer servir [**uart-bridge** de **roufsweb**](https://github.com/roufsweb/rp2040-usb-to-uart-bridge), copiar l'**u2f** a la unitat de l'**RP2040** al iniciar amb **BOOTMODE** i ja estarà llest per programar via **esptool**.

---

## 🛠️ Arquitectura del Maquinari (Pinout)

La comunicació sèrie i els perifèrics clau estan configurats de la següent manera:

| Component | Pin ESP-12F / Perifèric | Pin RP2040 (HackBat) | Descripció |
| :--- | :--- | :--- | :--- |
| **UART TX/RX** | TX (GPIO1) / RX (GPIO3) | GP1 (RX) / GP0 (TX) | Comunicació sèrie entre RP2040 i ESP-12F |
| **Indicador LED** | GPIO16 | - | LED integrat a l'ESP-12F (actiu en LOW) |
| **Pantalla OLED** | - | SDA (GP4) / SCL (GP5) | Pantalla I2C SH1106 (128x64) |
| **Botons** | - | GP22, GP26, GP27, GP28, GP29 | Navegació pel menú (Up, Down, Left, Right, Enter) |

---

## ⚠️ Resolució de l'Error de Programació (`Timed out waiting for packet header`)

Quan intentes programar l'ESP-12F a través del pont USB-UART de l'RP2040, és molt habitual trobar aquest error a l'esptool:

```text
Connecting....
Chip is ESP8266EX
Uploading stub...
A fatal esptool.py error occurred: Timed out waiting for packet header

```

### Solució Definitiva:

Com que el pont USB de l'RP2040 pot desbordar el buffer en intentar pujar l'stub de la RAM a alta velocitat, la solució és ometre l'stub fent servir la ROM nativa de l'ESP8266 mitjançant la bandera `--no-stub`:

1. A l'Arduino IDE, compila el codi i ves a **Sketch > Export compiled binary** per obtenir l'arxiu `.bin`.
2. Posar l'ESP-12F en mode *bootloader* manualment (manté premut el botó **BOOT**, reinicia i deixa anar).
3. Executa des de la terminal de comandes:
```bash
esptool --port COM6 --baud 115200 --no-stub write-flash 0x0 el_teu_fitxer.bin

```



---

## 💻 Codi de l'ESP-12F (Firmware del Scanner)

Aquest codi s'encarrega d'escoltar peticions per UART (`SCAN`), fer l'escaneig de xarxes Wi-Fi (incloent-hi les ocultes) i retornar una trama formatada. Inclou parpelleigs al LED del GPIO16 per confirmar l'arrencada i l'activitat.

```cpp
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
  digitalWrite(LED_PIN, LOW); // LED encès durant l'escaneig
  
  int n = WiFi.scanNetworks(false, true);  // Inclou xarxes ocultes
  
  digitalWrite(LED_PIN, HIGH); // Apaga el LED

  Serial.printf("N|%d\n", n < 0 ? 0 : n);
  for (int i = 0; i < n; i++) {
    String ssid = WiFi.SSID(i);
    ssid.replace("\n", " ");
    ssid.replace("\r", " ");
    // Format: R|rssi|channel|enc|bssid|ssid
    Serial.printf("R|%d|%d|%d|%s|%s\n",
                  WiFi.RSSI(i), WiFi.channel(i), (int)WiFi.encryptionType(i),
                  WiFi.BSSIDstr(i).c_str(), ssid.c_str());
  }
  Serial.println("END");
  WiFi.scanDelete();
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);

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
      digitalWrite(LED_PIN, LOW);
      Serial.println("PONG");
      delay(50);
      digitalWrite(LED_PIN, HIGH);
    }
  }
}

```

---

## 📡 Protocol de Comunicació UART

El format de comunicació entre l'ESP-12F i l'RP2040 segueix una estructura de línies de text delimitades per barres verticals (`|`):

* **Petició:** `SCAN\n`
* **Resposta de xarxes:** `R|<rssi>|<canal>|<encriptació>|<bssid>|<ssid>\n`
* **Final de transmissió:** `END\n`

```
