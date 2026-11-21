import machine
import time
import os
import sh1106
import sdcard

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

BTN_UP      = 22
BTN_LEFT    = 26
BTN_ENTER   = 27
BTN_RIGHT   = 28
BTN_DOWN    = 29

# ==========================================
# INICIALITZACIÓ MAQUINARI
# ==========================================
led_act = machine.Pin(LED_ACT_PIN, machine.Pin.OUT, value=0)
led_err = machine.Pin(LED_ERR_PIN, machine.Pin.OUT, value=0)
sd_detect = machine.Pin(SD_DET_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)

btns = {
    "UP":    machine.Pin(BTN_UP, machine.Pin.IN, machine.Pin.PULL_DOWN),
    "DOWN":  machine.Pin(BTN_DOWN, machine.Pin.IN, machine.Pin.PULL_DOWN),
    "LEFT":  machine.Pin(BTN_LEFT, machine.Pin.IN, machine.Pin.PULL_DOWN),
    "RIGHT": machine.Pin(BTN_RIGHT, machine.Pin.IN, machine.Pin.PULL_DOWN),
    "ENTER": machine.Pin(BTN_ENTER, machine.Pin.IN, machine.Pin.PULL_DOWN),
}

i2c = machine.I2C(0, sda=machine.Pin(I2C_SDA_PIN), scl=machine.Pin(I2C_SCL_PIN), freq=400000)
try:
    oled = sh1106.SH1106_I2C(128, 64, i2c, addr=OLED_ADDR, rotate=180)
except TypeError:
    oled = sh1106.SH1106_I2C(128, 64, i2c, addr=OLED_ADDR)

# ==========================================
# MUNTATGE SEGUR DE LA MICROSD
# ==========================================
spi = None
cs = None

def mount_sd():
    global spi, cs
    led_act.value(1)
    led_err.value(0)

    if sd_detect.value() == 0:
        raise OSError("NO HI HA SD (GP12=0)")

    try:
        os.umount("/sd")
    except OSError:
        pass

    cs = machine.Pin(SD_CS_PIN, machine.Pin.OUT, value=1)
    miso = machine.Pin(SD_MISO_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

    spi = machine.SPI(
        1,
        baudrate=250_000,
        polarity=0,
        phase=0,
        bits=8,
        firstbit=machine.SPI.MSB,
        sck=machine.Pin(SD_SCK_PIN),
        mosi=machine.Pin(SD_MOSI_PIN),
        miso=miso
    )
    machine.Pin(SD_MISO_PIN, pull=machine.Pin.PULL_UP)

    # 160 cicles de rellotge amb CS en alt abans d'inicialitzar
    cs.value(1)
    spi.write(b'\xFF' * 20)

    sd = sdcard.SDCard(spi, cs)
    machine.Pin(SD_MISO_PIN, pull=machine.Pin.PULL_UP)

    vfs = os.VfsFat(sd)
    os.mount(vfs, "/sd")
    led_act.value(0)

# ==========================================
# UTILITATS D'EXPLORACIÓ I FORMAT (20 CHARS)
# ==========================================
def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def fit_20(text):
    """Retalla o omple amb espais fins a exactament 20 caràcters."""
    if len(text) > 20:
        return text[:19] + "~"
    return text + (" " * (20 - len(text)))

def format_entry_20(name, is_dir):
    """Dona format a 20 caràcters preservant l'extensió en els fitxers."""
    prefix = "/" if is_dir and name != ".." else " "
    full = f"{prefix}{name}"
    
    if len(full) <= 20:
        return full + (" " * (20 - len(full)))
    
    # Si és un fitxer i té extensió (punt que no sigui el primer caràcter del nom)
    if not is_dir and "." in name[1:]:
        base, ext = name.rsplit(".", 1)
        ext_part = f".{ext}"
        # Reservem espai per: prefix (1) + base truncada + '~' (1) + '.ext'
        avail_base = 20 - 1 - 1 - len(ext_part)
        if avail_base >= 2:
            return f"{prefix}{base[:avail_base]}~{ext_part}"
            
    # Per a directoris o fitxers sense extensió (o extensions llarguíssimes)
    return full[:19] + "~"

def list_directory(path):
    """Retorna llista ordenada: primer carpetes, després fitxers."""
    led_act.value(1)
    dirs = []
    files = []
    
    if path != "/sd":
        dirs.append(("..", True, 0))

    try:
        entries = os.listdir(path)
    except OSError:
        led_act.value(0)
        return dirs

    for name in entries:
        full_path = f"{path}/{name}"
        try:
            st = os.stat(full_path)
            is_dir = (st[0] & 0x4000) != 0
            size = st[6]
            if is_dir:
                dirs.append((name, True, 0))
            else:
                files.append((name, False, size))
        except OSError:
            files.append((name, False, 0))

    dirs_sorted = [dirs[0]] + sorted(dirs[1:], key=lambda x: x[0].lower()) if path != "/sd" else sorted(dirs, key=lambda x: x[0].lower())
    files_sorted = sorted(files, key=lambda x: x[0].lower())
    led_act.value(0)
    return dirs_sorted + files_sorted

# ==========================================
# RENDERITZAT OLED (5 FILES VISIBLES + CAPÇALERA)
# ==========================================
VISIBLE_ROWS = 5

def draw_browser(current_path, items, sel_idx, scroll_offset):
    oled.fill(0)
    
    # Capçalera invertida (20 caràcters)
    header_txt = current_path if len(current_path) <= 20 else ".." + current_path[-18:]
    oled.fill_rect(0, 0, 128, 10, 1)
    oled.text(fit_20(header_txt), 0, 1, 0)

    if not items:
        oled.text(fit_20("(Directori buit)"), 0, 28, 1)
        oled.show()
        return

    for row in range(VISIBLE_ROWS):
        idx = scroll_offset + row
        if idx >= len(items):
            break
        
        name, is_dir, _ = items[idx]
        #prefix = "/" if is_dir and name != ".." else " "
        label = format_entry_20(name, is_dir)
        y = 13 + (row * 10)

        if idx == sel_idx:
            # Barra de selecció invertida
            oled.fill_rect(0, y - 1, 128, 10, 1)
            oled.text(label, 0, y, 0)
        else:
            oled.text(label, 0, y, 1)

    oled.show()

def draw_file_info(current_path, name, size_bytes):
    oled.fill(0)
    oled.fill_rect(0, 0, 128, 10, 1)
    oled.text(fit_20("INFO FITXER"), 0, 1, 0)

    if len(name) <= 20:
        oled.text(fit_20(name), 0, 14, 1)
        oled.text(fit_20(f"Mida: {format_size(size_bytes)}"), 0, 27, 1)
        oled.text(fit_20(f"Bytes: {size_bytes}"), 0, 38, 1)
    else:
        # Partim el nom en dues línies (fins a 40 caràcters en total)
        line1 = name[:20]
        line2 = name[20:40]
        if len(name) > 40:
            line2 = name[20:39] + "~"
        
        oled.text(fit_20(line1), 0, 13, 1)
        oled.text(fit_20(line2), 0, 23, 1)
        oled.text(fit_20(f"Mida: {format_size(size_bytes)}"), 0, 34, 1)
        oled.text(fit_20(f"Bytes: {size_bytes}"), 0, 44, 1)

    oled.text(fit_20("< LEFT per tornar"), 0, 55, 1)
    oled.show()

def draw_error(msg_line1, msg_line2=""):
    led_err.value(1)
    oled.fill(0)
    oled.fill_rect(0, 0, 128, 10, 1)
    oled.text(fit_20("ERROR MICROSD"), 0, 1, 0)
    oled.text(fit_20(msg_line1), 0, 22, 1)
    oled.text(fit_20(msg_line2), 0, 36, 1)
    oled.text(fit_20("Prem ENTER reintent"), 0, 53, 1)
    oled.show()

# ==========================================
# LECTURA DE BOTONS AMB ANTIREBOT I REPETICIÓ
# ==========================================
def read_button():
    for name, pin in btns.items():
        if pin.value() == 1:
            time.sleep_ms(140) # Velocitat còmoda per desplaçar-se per llistes
            return name
    return None

# ==========================================
# BUCLE PRINCIPAL DE L'EXPLORADOR
# ==========================================
def run_explorer():
    while True:
        try:
            mount_sd()
            break
        except Exception as e:
            draw_error("Insereix la SD", str(e))
            while True:
                if sd_detect.value() == 1 or btns["ENTER"].value() == 1:
                    time.sleep_ms(250)
                    break
                time.sleep_ms(50)

    current_path = "/sd"
    items = list_directory(current_path)
    sel_idx = 0
    scroll_offset = 0
    viewing_file = False

    draw_browser(current_path, items, sel_idx, scroll_offset)

    while True:
        # Vigilància d'extracció de targeta en calent
        if sd_detect.value() == 0:
            draw_error("SD extreta!", "Insereix per seguir")
            while sd_detect.value() == 0:
                time.sleep_ms(100)
            time.sleep_ms(300)
            run_explorer()
            return

        btn = read_button()
        if not btn:
            time.sleep_ms(20)
            continue

        if viewing_file:
            if btn in ("LEFT", "ENTER"):
                viewing_file = False
                draw_browser(current_path, items, sel_idx, scroll_offset)
            continue

        if btn == "UP" and items:
            sel_idx = (sel_idx - 1) % len(items)
            if sel_idx < scroll_offset:
                scroll_offset = sel_idx
            elif sel_idx == len(items) - 1:
                scroll_offset = max(0, len(items) - VISIBLE_ROWS)
            draw_browser(current_path, items, sel_idx, scroll_offset)

        elif btn == "DOWN" and items:
            sel_idx = (sel_idx + 1) % len(items)
            if sel_idx >= scroll_offset + VISIBLE_ROWS:
                scroll_offset = sel_idx - VISIBLE_ROWS + 1
            elif sel_idx == 0:
                scroll_offset = 0
            draw_browser(current_path, items, sel_idx, scroll_offset)

        elif btn in ("ENTER", "RIGHT") and items:
            name, is_dir, size = items[sel_idx]
            if is_dir:
                if name == "..":
                    current_path = current_path.rsplit("/", 1)[0] or "/sd"
                else:
                    current_path = f"{current_path}/{name}"
                items = list_directory(current_path)
                sel_idx = 0
                scroll_offset = 0
                draw_browser(current_path, items, sel_idx, scroll_offset)
            else:
                viewing_file = True
                draw_file_info(current_path, name, size)

        elif btn == "LEFT":
            if current_path != "/sd":
                current_path = current_path.rsplit("/", 1)[0] or "/sd"
                items = list_directory(current_path)
                sel_idx = 0
                scroll_offset = 0
                draw_browser(current_path, items, sel_idx, scroll_offset)

run_explorer()
