"""
Pico DAC Controller - Phase 4
Receives 4 comma-separated values over USB serial
and sets MCP4728 DAC channels accordingly.

Serial format: throttle,yaw,pitch,roll\n
Values: 0-4095 (12-bit DAC range)
Example: 0,2048,2048,2048\n

Safety features:
- On boot: throttle=0, yaw/pitch/roll=center (2048)
- On serial timeout (500ms): same safe defaults
- Killswitch: send "KILL\n" to immediately set safe defaults
"""

from machine import I2C, Pin
import sys
import select
import time

# === Setup I2C and DAC ===
i2c = I2C(0, sda=Pin(4), scl=Pin(5))

# Onboard LED for status feedback
led = Pin("LED", Pin.OUT)

# Safe default values
SAFE_THROTTLE = 0       # 0V - motors off
SAFE_CENTER = 2048      # ~1.65V - neutral position

# Timeout: if no serial data for this many ms, go to safe defaults
TIMEOUT_MS = 500

def set_dac(channel, value):
    """Set a single DAC channel (0-3) to a value (0-4095)."""
    value = max(0, min(4095, value))  # Clamp to valid range
    data = bytearray(3)
    data[0] = 0x40 | ((channel & 0x03) << 1)
    data[1] = (value >> 8) & 0x0F
    data[2] = value & 0xFF
    i2c.writeto(0x60, data)

def set_all_channels(throttle, yaw, pitch, roll):
    """Set all 4 DAC channels at once."""
    set_dac(0, throttle)
    set_dac(1, yaw)
    set_dac(2, pitch)
    set_dac(3, roll)

def set_safe_defaults():
    """Immediately set all channels to safe values."""
    set_all_channels(SAFE_THROTTLE, SAFE_CENTER, SAFE_CENTER, SAFE_CENTER)

def parse_command(line):
    """Parse a serial command. Returns (throttle, yaw, pitch, roll) or None."""
    line = line.strip()
    
    # Killswitch command
    if line == "KILL":
        return (SAFE_THROTTLE, SAFE_CENTER, SAFE_CENTER, SAFE_CENTER)
    
    # Parse comma-separated values
    try:
        parts = line.split(",")
        if len(parts) != 4:
            return None
        values = [int(p.strip()) for p in parts]
        # Clamp all values to 0-4095
        values = [max(0, min(4095, v)) for v in values]
        return tuple(values)
    except (ValueError, IndexError):
        return None

# === Main Loop ===

# Set safe defaults on boot
set_safe_defaults()
print("READY")  # Tell Mac we're alive

# For reading serial input
input_buffer = ""
last_data_time = time.ticks_ms()

# Blink LED once to show we're running
led.on()
time.sleep_ms(200)
led.off()

while True:
    # Check if there's serial data available
    if select.select([sys.stdin], [], [], 0)[0]:
        char = sys.stdin.read(1)
        if char == "\n":
            # We have a complete command
            result = parse_command(input_buffer)
            if result is not None:
                throttle, yaw, pitch, roll = result
                set_all_channels(throttle, yaw, pitch, roll)
                led.on()  # LED on when receiving valid commands
                print("OK")  # Acknowledge to Mac
            input_buffer = ""
            last_data_time = time.ticks_ms()
        else:
            input_buffer += char
    
    # Check for timeout - no data for 500ms
    if time.ticks_diff(time.ticks_ms(), last_data_time) > TIMEOUT_MS:
        set_safe_defaults()
        led.off()  # LED off when in timeout/safe mode
        last_data_time = time.ticks_ms()  # Reset so we don't spam the DAC
    
    time.sleep_ms(1)  # Small delay to prevent busy-waiting
