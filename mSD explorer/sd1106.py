# SH1106 OLED driver for MicroPython
# Supports 128x64 I2C displays
# Based on the standard MicroPython SH1106 driver

import framebuf
from micropython import const

SET_CONTRAST        = const(0x81)
SET_NORM_INV        = const(0xa6)
SET_DISP            = const(0xae)
SET_MEM_ADDR        = const(0x20)
SET_COL_ADDR        = const(0x21)
SET_PAGE_ADDR       = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP       = const(0xa0)
SET_MUX_RATIO       = const(0xa8)
SET_COM_OUT_DIR     = const(0xc0)
SET_DISP_OFFSET     = const(0xd3)
SET_COM_PIN_CFG     = const(0xda)
SET_DISP_CLK_DIV    = const(0xd5)
SET_PRECHARGE       = const(0xd9)
SET_VCOM_DESEL      = const(0xdb)
SET_CHARGE_PUMP     = const(0x8d)


class SH1106_I2C:
    def __init__(self, width, height, i2c, addr=0x3C):
        self.width   = width
        self.height  = height
        self.i2c     = i2c
        self.addr    = addr
        self.pages   = height // 8
        self.buf     = bytearray(self.pages * width)
        self.fb      = framebuf.FrameBuffer(self.buf, width, height, framebuf.MONO_VLSB)
        self._init_display()

    def _write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes([0x00, cmd]))

    def _init_display(self):
        cmds = [
            SET_DISP | 0x00,          # display off
            SET_MEM_ADDR, 0x00,       # horizontal addressing
            SET_DISP_START_LINE,      # start line = 0
            SET_SEG_REMAP | 0x01,     # column addr 127 mapped to SEG0
            SET_MUX_RATIO, self.height - 1,
            SET_COM_OUT_DIR | 0x08,   # scan from COM[N] to COM0
            SET_DISP_OFFSET, 0x00,
            SET_COM_PIN_CFG, 0x12,
            SET_DISP_CLK_DIV, 0x80,
            SET_PRECHARGE, 0xf1,
            SET_VCOM_DESEL, 0x30,
            SET_CONTRAST, 0xff,
            SET_CHARGE_PUMP, 0x14,    # enable charge pump
            SET_NORM_INV,             # normal (non-inverted) display
            SET_DISP | 0x01,          # display on
        ]
        for cmd in cmds:
            self._write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweroff(self):
        self._write_cmd(SET_DISP | 0x00)

    def poweron(self):
        self._write_cmd(SET_DISP | 0x01)

    def contrast(self, contrast):
        self._write_cmd(SET_CONTRAST)
        self._write_cmd(contrast)

    def invert(self, invert):
        self._write_cmd(SET_NORM_INV | (invert & 1))

    def fill(self, col):
        self.fb.fill(col)

    def pixel(self, x, y, col):
        self.fb.pixel(x, y, col)

    def text(self, string, x, y, col=1):
        self.fb.text(string, x, y, col)

    def hline(self, x, y, w, col):
        self.fb.hline(x, y, w, col)

    def vline(self, x, y, h, col):
        self.fb.vline(x, y, h, col)

    def line(self, x1, y1, x2, y2, col):
        self.fb.line(x1, y1, x2, y2, col)

    def rect(self, x, y, w, h, col):
        self.fb.rect(x, y, w, h, col)

    def fill_rect(self, x, y, w, h, col):
        self.fb.fill_rect(x, y, w, h, col)

    def show(self):
        # SH1106 uses page addressing, 132 columns internally (offset 2)
        for page in range(self.pages):
            self._write_cmd(0xB0 | page)       # set page
            self._write_cmd(0x02)              # col low nibble  (offset 2)
            self._write_cmd(0x10)              # col high nibble
            # write 128 bytes of pixel data for this page
            data = bytearray(1 + self.width)
            data[0] = 0x40  # data mode
            data[1:] = self.buf[page * self.width:(page + 1) * self.width]
            self.i2c.writeto(self.addr, data)

