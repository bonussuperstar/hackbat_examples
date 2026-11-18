#include <Wire.h>
#include <U8g2lib.h>

#define I2C_SDA   4
#define I2C_SCL   5
#define UART_TX   0   // GP0 -> wifi_rxd -> ESP GPIO3
#define UART_RX   1   // GP1 <- wifi_txd <- ESP GPIO1

#define BTN_UP    22
#define BTN_LEFT  26  // assumed
#define BTN_ENTER 27  // assumed
#define BTN_RIGHT 28  // assumed
#define BTN_DOWN  29  // assumed

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

#define MAX_NET 24
struct Net {
  String ssid, bssid;
  int rssi, ch, enc;
};
Net nets[MAX_NET];
int netCount = 0;

enum State { MENU, LIST, DETAIL, CHANNELS, ERROR_ESP };
State state = ERROR_ESP; // Comencem en estat d'error fins validar la connexió
int menuSel = 0, listSel = 0, listTop = 0;
const int VISIBLE = 5;
const char* menuItems[] = { "WiFi list", "Channel graph" };
const int MENU_N = 2;

// ---------- buttons (pressed = HIGH) ----------
struct Btn { uint8_t pin; bool last; unsigned long t; };
Btn btns[] = {
  { BTN_UP, false, 0 }, { BTN_DOWN, false, 0 }, { BTN_LEFT, false, 0 },
  { BTN_RIGHT, false, 0 }, { BTN_ENTER, false, 0 }
};
enum { B_UP, B_DOWN, B_LEFT, B_RIGHT, B_ENTER };

bool pressed(int i) {
  bool now = digitalRead(btns[i].pin) == HIGH;
  bool fired = now && !btns[i].last && millis() - btns[i].t > 150;
  if (fired) btns[i].t = millis();
  btns[i].last = now;
  return fired;
}

// ---------- helpers ----------
const char* encName(int e) {
  switch (e) {
    case 7: return "Open";
    case 5: return "WEP";
    case 2: return "WPA";
    case 4: return "WPA2";
    case 8: return "WPA/WPA2";
    default: return "?";
  }
}

void showMessage(const char* msg) {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(10, 36, msg);
  u8g2.sendBuffer();
}

void drawErrorScreen() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(10, 20, "CRITICAL ERROR:");
  u8g2.setFont(u8g2_font_5x8_tr);
  u8g2.drawStr(10, 38, "ESP-12F no respon!");
  u8g2.drawStr(10, 52, "Comprova connexio/UART");
  u8g2.sendBuffer();
}

// Parse "R|rssi|ch|enc|bssid|ssid"
bool parseNet(const String &l, Net &n) {
  int p1 = l.indexOf('|', 2);
  int p2 = l.indexOf('|', p1 + 1);
  int p3 = l.indexOf('|', p2 + 1);
  int p4 = l.indexOf('|', p3 + 1);
  if (p1 < 0 || p2 < 0 || p3 < 0 || p4 < 0) return false;
  n.rssi  = l.substring(2, p1).toInt();
  n.ch    = l.substring(p1 + 1, p2).toInt();
  n.enc   = l.substring(p2 + 1, p3).toInt();
  n.bssid = l.substring(p3 + 1, p4);
  n.ssid  = l.substring(p4 + 1);
  if (n.ssid.length() == 0) n.ssid = "<hidden>";
  return true;
}

bool scanNetworks() {
  while (Serial1.available()) Serial1.read();  // flush boot noise
  Serial1.print("SCAN\n");

  netCount = 0;
  unsigned long start = millis();
  bool done = false;
  while (!done && millis() - start < 8000) {
    if (!Serial1.available()) continue;
    String line = Serial1.readStringUntil('\n');
    line.trim();
    if (line == "END") done = true;
    else if (line.startsWith("R|") && netCount < MAX_NET) {
      if (parseNet(line, nets[netCount])) netCount++;
    }
  }

  // Si no rebem cap línia ni el missatge END, considerem fallada de comunicació
  if (!done && netCount == 0) {
    return false;
  }

  // sort by RSSI, strongest first
  for (int i = 0; i < netCount - 1; i++)
    for (int j = i + 1; j < netCount; j++)
      if (nets[j].rssi > nets[i].rssi) { Net t = nets[i]; nets[i] = nets[j]; nets[j] = t; }
  listSel = 0;
  listTop = 0;
  return true;
}

// ---------- screens ----------
void drawMenu() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(30, 10, "HackBat WiFi");
  u8g2.drawHLine(0, 13, 128);
  for (int i = 0; i < MENU_N; i++) {
    int y = 28 + i * 14;
    if (i == menuSel) {
      u8g2.drawBox(0, y - 10, 128, 13);
      u8g2.setDrawColor(0);
      u8g2.drawStr(6, y, menuItems[i]);
      u8g2.setDrawColor(1);
    } else {
      u8g2.drawStr(6, y, menuItems[i]);
    }
  }
  u8g2.sendBuffer();
}

void drawList() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_5x8_tr);
  char hdr[24];
  snprintf(hdr, sizeof(hdr), "Networks: %d", netCount);
  u8g2.drawStr(0, 8, hdr);
  u8g2.drawStr(86, 8, "R=rescan");
  u8g2.drawHLine(0, 10, 128);
  if (netCount == 0) u8g2.drawStr(10, 36, "No networks found");
  for (int i = 0; i < VISIBLE; i++) {
    int idx = listTop + i;
    if (idx >= netCount) break;
    int y = 20 + i * 10;
    char line[40];
    String s = nets[idx].ssid;
    if (s.length() > 15) s = s.substring(0, 15);
    snprintf(line, sizeof(line), "%-15s%4d c%d", s.c_str(), nets[idx].rssi, nets[idx].ch);
    if (idx == listSel) {
      u8g2.drawBox(0, y - 8, 128, 10);
      u8g2.setDrawColor(0);
      u8g2.drawStr(1, y, line);
      u8g2.setDrawColor(1);
    } else {
      u8g2.drawStr(1, y, line);
    }
  }
  u8g2.sendBuffer();
}

void drawDetail() {
  Net &n = nets[listSel];
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x12_tr);
  String s = n.ssid;
  if (s.length() > 21) s = s.substring(0, 21);
  u8g2.drawStr(0, 10, s.c_str());
  u8g2.drawHLine(0, 13, 128);
  char buf[32];
  snprintf(buf, sizeof(buf), "RSSI: %d dBm", n.rssi);          u8g2.drawStr(0, 26, buf);
  snprintf(buf, sizeof(buf), "Channel: %d", n.ch);             u8g2.drawStr(0, 38, buf);
  snprintf(buf, sizeof(buf), "Security: %s", encName(n.enc));  u8g2.drawStr(0, 50, buf);
  u8g2.setFont(u8g2_font_5x8_tr);
  u8g2.drawStr(0, 62, n.bssid.c_str());
  u8g2.sendBuffer();
}

void drawChannels() {
  int best[14], cnt[14];
  for (int c = 0; c < 14; c++) { best[c] = -100; cnt[c] = 0; }
  for (int i = 0; i < netCount; i++) {
    int c = nets[i].ch;
    if (c < 1 || c > 13) continue;
    cnt[c]++;
    if (nets[i].rssi > best[c]) best[c] = nets[i].rssi;
  }
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_5x8_tr);
  u8g2.drawStr(0, 8, "Channels (2.4GHz)");
  u8g2.drawStr(86, 8, "R=rescan");
  const int baseY = 54, maxH = 38, w = 9;
  for (int c = 1; c <= 13; c++) {
    int x = (c - 1) * w + 5;
    if (cnt[c] > 0) {
      int h = map(constrain(best[c], -100, -30), -100, -30, 2, maxH);
      u8g2.drawBox(x, baseY - h, w - 2, h);
    } else {
      u8g2.drawHLine(x, baseY, w - 2);
    }
    char t[4];
    snprintf(t, sizeof(t), "%d", c);
    u8g2.drawStr(x + (c > 9 ? 0 : 1), 63, t);
  }
  u8g2.sendBuffer();
}

// ---------- setup / loop ----------
void setup() {
  for (auto &b : btns) pinMode(b.pin, INPUT_PULLDOWN);  // pressed = HIGH

  Wire.setSDA(I2C_SDA);
  Wire.setSCL(I2C_SCL);
  Wire.begin();
  u8g2.begin();

  Serial1.setTX(UART_TX);
  Serial1.setRX(UART_RX);
  Serial1.begin(115200);
  Serial1.setTimeout(200);

  showMessage("Starting ESP...");
  delay(2000);  // Donar temps a l'ESP-12F per arrencar

  // Comprovació inicial: si falla el primer escaneig, bloquegem a ERROR_ESP
  if (scanNetworks()) {
    state = MENU;
  } else {
    state = ERROR_ESP;
  }
}

void loop() {
  // Si estem en estat d'error crític, mostrem la pantalla d'error i no deixem avançar
  if (state == ERROR_ESP) {
    drawErrorScreen();
    // Opcional: permetre reintentar si es prem ENTER o RIGHT
    if (pressed(B_ENTER) || pressed(B_RIGHT)) {
      showMessage("Reconnecting...");
      delay(500);
      if (scanNetworks()) {
        state = MENU;
      }
    }
    delay(100);
    return;
  }

  bool up = pressed(B_UP), down = pressed(B_DOWN);
  bool left = pressed(B_LEFT), right = pressed(B_RIGHT), enter = pressed(B_ENTER);

  switch (state) {
    case MENU:
      if (up && menuSel > 0) menuSel--;
      if (down && menuSel < MENU_N - 1) menuSel++;
      if (enter || right) state = (menuSel == 0) ? LIST : CHANNELS;
      break;
    case LIST:
      if (up && listSel > 0) listSel--;
      if (down && listSel < netCount - 1) listSel++;
      if (listSel < listTop) listTop = listSel;
      if (listSel >= listTop + VISIBLE) listTop = listSel - VISIBLE + 1;
      if (enter && netCount > 0) state = DETAIL;
      if (right) {
        if (!scanNetworks()) {
          state = ERROR_ESP; // Si cau durant l'ús, salta a pantalla d'error
        }
      }
      if (left) state = MENU;
      break;
    case DETAIL:
      if (left || enter) state = LIST;
      break;
    case CHANNELS:
      if (right) {
        if (!scanNetworks()) {
          state = ERROR_ESP;
        }
      }
      if (left) state = MENU;
      break;
    case ERROR_ESP:
      break;
  }

  switch (state) {
    case MENU:     drawMenu();     break;
    case LIST:     drawList();     break;
    case DETAIL:   drawDetail();   break;
    case CHANNELS: drawChannels(); break;
    case ERROR_ESP: drawErrorScreen(); break;
  }
  delay(20);
}