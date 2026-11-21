import machine
import time
import os
import gc
import sh1106

# ==========================================
# PINOUT HACKBAT RP2040
# ==========================================
I2C_SDA_PIN = 4
I2C_SCL_PIN = 5
OLED_ADDR   = 0x3C

SD_MISO_PIN = 8
SD_CS_PIN   = 9
SD_SCK_PIN  = 10
SD_MOSI_PIN = 11
SD_DET_PIN  = 12    # Actiu HIGH quan hi ha targeta inserida

LED_ACT_PIN = 14
LED_ERR_PIN = 15
BTN_ENTER   = 27

# ==========================================
# INICIALITZACIÓ MAQUINARI BÀSIC
# ==========================================
led_act = machine.Pin(LED_ACT_PIN, machine.Pin.OUT)
led_err = machine.Pin(LED_ERR_PIN, machine.Pin.OUT)
btn_enter = machine.Pin(BTN_ENTER, machine.Pin.IN, machine.Pin.PULL_DOWN)
sd_detect = machine.Pin(SD_DET_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)

i2c = machine.I2C(0, sda=machine.Pin(I2C_SDA_PIN), scl=machine.Pin(I2C_SCL_PIN), freq=400000)
try:
    oled = sh1106.SH1106_I2C(128, 64, i2c, addr=OLED_ADDR, rotate=180)
except TypeError:
    oled = sh1106.SH1106_I2C(128, 64, i2c, addr=OLED_ADDR)

# ==========================================
# GESTIÓ DE PANTALLA (MÀX 20 CARÀCTERS/LÍNIA)
# ==========================================
oled_lines = []

def log_console(msg):
    ts = time.ticks_ms()
    print(f"[{ts:08d} ms] {msg}")

def oled_reset(title="TEST MICROSD HACKBAT"):
    global oled_lines
    oled_lines = []
    oled.fill(0)
    oled.fill_rect(0, 0, 128, 10, 1)
    oled.text(title[:20].center(20), 0, 1, 0)
    oled.show()

def oled_step(text, is_error=False):
    global oled_lines
    prefix = "!" if is_error else ">"
    line = f"{prefix}{text}"[:20]
    oled_lines.append((line, is_error))
    if len(oled_lines) > 5:
        oled_lines.pop(0)
    
    oled.fill_rect(0, 12, 128, 52, 0)
    for idx, (txt, err) in enumerate(oled_lines):
        y = 13 + (idx * 10)
        if err:
            oled.fill_rect(0, y - 1, 128, 9, 1)
            oled.text(txt, 0, y, 0)
        else:
            oled.text(txt, 0, y, 1)
    oled.show()

# ==========================================
# DIAGNÒSTIC SPI DE BAIX NIVELL (RAW CMD0)
# ==========================================
def raw_sd_probe(spi, cs):
    log_console("Iniciant sonda SPI de baix nivell (CMD0)...")
    cs.value(1)
    # 160 cicles de rellotge per netejar i despertar la targeta
    spi.write(b'\xFF' * 20)
    
    cs.value(0)
    spi.write(b'\x40\x00\x00\x00\x00\x95')
    
    resp = 0xFF
    for attempt in range(16):
        r = spi.read(1, 0xFF)[0]
        log_console(f"  CMD0 intent {attempt+1}: byte rebut = 0x{r:02X}")
        if r != 0xFF:
            resp = r
            break
    cs.value(1)
    spi.write(b'\xFF')
    return resp

# ==========================================
# BATERIA DE PROVES PRINCIPAL
# ==========================================
def run_sd_diagnostics():
    led_act.value(1)
    led_err.value(0)
    oled_reset("TEST MICROSD v1.3")
    
    print("\n" + "="*50)
    log_console("INICIANT DIAGNÒSTIC COMPLET DE MICROSD")
    log_console(f"Freqüència CPU RP2040: {machine.freq() / 1_000_000:.1f} MHz")
    log_console(f"RAM lliure inicial: {gc.mem_free()} bytes")
    log_console(f"Pins -> MISO:{SD_MISO_PIN} CS:{SD_CS_PIN} SCK:{SD_SCK_PIN} MOSI:{SD_MOSI_PIN} DET:{SD_DET_PIN}")
    print("="*50)

    spi = None
    cs = None

    try:
        # 1. VERIFICACIÓ FÍSICA PEL PIN SD_DETECT (GPIO12 - ACTIU HIGH)
        oled_step("1.Pin Detect GP12")
        det_val = sd_detect.value()
        log_console(f"PAS 1: Llegint pin físic SD_DETECT (GP{SD_DET_PIN})...")
        log_console(f"  Estat lògic GP{SD_DET_PIN} = {det_val} ({'HIGH / 3.3V' if det_val == 1 else 'LOW / 0V'})")
        
        if det_val == 1:
            oled_step("GP12=1: SD PRESENT")
            log_console("  OK: Targeta inserida detectada (GP12 = HIGH).")
        else:
            oled_step("ERR: GP12=0 NO SD!", True)
            log_console("  ERROR CRÍTIC: GP12 en LOW (0). No hi ha cap microSD inserida.")
            raise OSError("Targeta absent segons pin GP12")

        # 2. VERIFICACIÓ DEL DRIVER SDCARD
        oled_step("2.Driver sdcard.py")
        log_console("PAS 2: Important mòdul 'sdcard'...")
        try:
            import sdcard
            log_console("  OK: Mòdul 'sdcard' carregat correctament.")
        except ImportError as e:
            oled_step("ERR: Falta sdcard.py", True)
            log_console(f"  ERROR CRÍTIC: No s'ha trobat sdcard.py ({e})")
            raise RuntimeError("Falta llibreria sdcard.py")

        # 3. INICIALITZACIÓ BUS SPI1 AMB PULL-UP A MISO
        oled_step("3.Bus SPI1 / CMD0")
        log_console("PAS 3: Configurant SPI(1) a 250 kHz amb PULL_UP a MISO (GP8)...")
        cs = machine.Pin(SD_CS_PIN, machine.Pin.OUT, value=1)
        miso_pin = machine.Pin(SD_MISO_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        
        spi = machine.SPI(
            1,
            baudrate=250_000,
            polarity=0,
            phase=0,
            bits=8,
            firstbit=machine.SPI.MSB,
            sck=machine.Pin(SD_SCK_PIN),
            mosi=machine.Pin(SD_MOSI_PIN),
            miso=miso_pin
        )
        # Reafirmem el PULL_UP intern després que SPI inicialitzi el pad GPIO8
        machine.Pin(SD_MISO_PIN, pull=machine.Pin.PULL_UP)

        raw_r1 = raw_sd_probe(spi, cs)
        if raw_r1 == 0x01:
            oled_step("SPI OK (R1=0x01)")
            log_console("  OK: Targeta en estat Idle (R1 = 0x01).")
        else:
            oled_step(f"SPI R1=0x{raw_r1:02X}", True)
            log_console(f"  ERROR: Resposta inesperada a CMD0: 0x{raw_r1:02X}")
            raise OSError(f"CMD0 R1=0x{raw_r1:02X}")

        # 4. INICIALITZACIÓ DEL CONTROLADOR SD
        oled_step("4.Init protocol SD")
        log_console("PAS 4: Inicialitzant protocol SD i llegint CSD...")
        t0 = time.ticks_us()
        sd = sdcard.SDCard(spi, cs)
        # Tornem a assegurar PULL_UP a MISO un cop sdcard apuja el baudrate
        machine.Pin(SD_MISO_PIN, pull=machine.Pin.PULL_UP)
        t_init = time.ticks_diff(time.ticks_us(), t0)
        
        sectors = sd.sectors
        size_mb = (sectors * 512) / (1024 * 1024)
        size_gb = size_mb / 1024
        log_console(f"  OK: Inicialització en {t_init} us | Sectors: {sectors} | Mida: {size_mb:.2f} MB ({size_gb:.2f} GB)")
        oled_step(f"Mida: {size_mb:.0f} MB")

        # 5. MUNTATGE DEL SISTEMA DE FITXERS (VFS / FAT)
        oled_step("5.Muntant VFS FAT")
        log_console("PAS 5: Muntant sistema de fitxers a '/sd'...")
        try:
            os.umount("/sd")
        except OSError:
            pass
            
        vfs = os.VfsFat(sd)
        os.mount(vfs, "/sd")
        
        stat = os.statvfs("/sd")
        block_size = stat[0]
        total_fs_mb = (block_size * stat[2]) / (1024 * 1024)
        free_fs_mb = (block_size * stat[3]) / (1024 * 1024)
        
        log_console(f"  OK: Muntat a /sd | Clúster: {block_size} B | Total: {total_fs_mb:.2f} MB | Lliure: {free_fs_mb:.2f} MB")
        root_files = os.listdir("/sd")
        log_console(f"  Fitxers a l'arrel ({len(root_files)} elements): {root_files}")
        oled_step(f"Lliure: {free_fs_mb:.0f} MB")

        # 6. PROVA D'ESCRIPTURA I LECTURA AMB INTEGRITAT
        oled_step("6.Test R/W Dades")
        log_console("PAS 6: Executant prova d'escriptura, lectura i verificació byte a byte...")
        test_file = "/sd/_hb_test.bin"
        payload = bytes([(i * 73 + 41) & 0xFF for i in range(4096)])
        
        t0 = time.ticks_us()
        with open(test_file, "wb") as f:
            written = f.write(payload)
            f.flush()
        t_write = time.ticks_diff(time.ticks_us(), t0)
        write_kbps = (written / 1024) / (t_write / 1_000_000)

        t0 = time.ticks_us()
        with open(test_file, "rb") as f:
            read_back = f.read()
        t_read = time.ticks_diff(time.ticks_us(), t0)
        read_kbps = (len(read_back) / 1024) / (t_read / 1_000_000)

        log_console(f"  Escriptura: {write_kbps:.1f} KB/s ({t_write} us) | Lectura: {read_kbps:.1f} KB/s ({t_read} us)")

        if read_back == payload:
            oled_step("R/W CRC: CORRECTE")
            log_console("  OK: Verificació bit a bit superada sense errors.")
        else:
            oled_step("ERR: Dades corruptes", True)
            log_console("  ERROR: Les dades llegides difereixen de les escrites!")
            raise OSError("Corrupció de dades en R/W")

        # 7. NETEJA I DESMUNTATGE
        os.remove(test_file)
        os.umount("/sd")
        log_console("PAS 7: Fitxer temporal eliminat i /sd desmuntat.")
        
        oled_step("TEST COMPLET: OK!")
        log_console("RESULTAT FINAL: TOTES LES PROVES SUPERADES AMB ÈXIT.")
        led_act.value(0)

    except Exception as exc:
        led_act.value(0)
        led_err.value(1)
        err_type = type(exc).__name__
        err_msg = str(exc)
        log_console(f"EXCEPCIÓ CAPTURADA [{err_type}]: {err_msg}")
        oled_step(f"{err_type[:19]}", True)
        if err_msg:
            oled_step(f"{err_msg[:19]}", True)
        
        if cs:
            cs.value(1)
        if spi:
            spi.deinit()
        try:
            os.umount("/sd")
        except Exception:
            pass

# ==========================================
# EXECUCIÓ I BUCLE DE REPETICIÓ
# ==========================================
run_sd_diagnostics()
log_console("Prem ENTER (GP27) o insereix/treu la SD per repetir el diagnòstic.")

last_det_state = sd_detect.value()

while True:
    curr_det_state = sd_detect.value()
    if curr_det_state != last_det_state:
        time.sleep_ms(250)
        last_det_state = sd_detect.value()
        log_console(f"Canvi detectat a GP12 (nou estat: {last_det_state}). Reexecutant...")
        run_sd_diagnostics()

    if btn_enter.value() == 1:
        time.sleep_ms(200)
        run_sd_diagnostics()
        while btn_enter.value() == 1:
            time.sleep_ms(20)
    time.sleep_ms(50)
