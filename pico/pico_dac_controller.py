from machine import I2C, Pin
import sys, select, time
i2c = I2C(0, sda=Pin(4), scl=Pin(5))
led = Pin('LED', Pin.OUT)
TIMEOUT_MS = 500
NEUTRAL = 2048
def set_dac(ch, val):
    val = max(0, min(4095, val))
    d = bytearray(3)
    d[0] = 0x40 | ((ch & 3) << 1)
    d[1] = (val >> 8) & 0x0F
    d[2] = val & 0xFF
    i2c.writeto(0x60, d)
def set_all(t, y, p, r):
    set_dac(0,t); set_dac(1,y); set_dac(2,p); set_dac(3,r)
def safe():
    set_all(0, NEUTRAL, NEUTRAL, NEUTRAL)
def parse(line):
    line = line.strip()
    if line == 'KILL': return (0, NEUTRAL, NEUTRAL, NEUTRAL)
    try:
        parts = line.split(',')
        if len(parts) != 4: return None
        return tuple(max(0, min(4095, int(p))) for p in parts)
    except: return None
safe()
print('READY')
buf = ''
last = time.ticks_ms()
led.on(); time.sleep_ms(200); led.off()
while True:
    if select.select([sys.stdin], [], [], 0)[0]:
        c = sys.stdin.read(1)
        if c == '\n':
            r = parse(buf)
            if r: set_all(*r); led.on(); print('OK')
            buf = ''
            last = time.ticks_ms()
        else: buf += c
    if time.ticks_diff(time.ticks_ms(), last) > TIMEOUT_MS:
        safe(); led.off(); last = time.ticks_ms()
    time.sleep_ms(1)