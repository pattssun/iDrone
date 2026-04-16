"""
Mac DAC Sender - Phase 6 (pots removed)
Sends 4 channel values to the Pico over USB serial.

Controls:
  W/S              - throttle up/down
  A/D              - yaw left/right
  Arrow Up/Down    - pitch forward/back
  Arrow Left/Right - roll left/right
  C                - CENTER all (2048 / 1.65V)
  B                - BIND sequence (throttle max then zero)
  K                - KILLSWITCH (throttle 0, rest center)
  Q                - quit
  +/-              - change step size

Requires: pip install pyserial
"""

import serial
import serial.tools.list_ports
import time
import sys
import select
import os

NEUTRAL = 2048

def find_pico_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "usbmodem" in port.device.lower() or "pico" in port.description.lower():
            return port.device
    print("Available ports:")
    for port in ports:
        print(f"  {port.device} - {port.description}")
    return None

def main():
    port_name = find_pico_port()
    if port_name is None:
        print("Could not auto-detect Pico. Enter port manually:")
        port_name = input("> ").strip()

    print(f"Connecting to {port_name}...")
    ser = serial.Serial(port_name, 115200, timeout=0.1)
    time.sleep(1)

    print("Waiting for Pico...")
    start = time.time()
    while time.time() - start < 5:
        line = ser.readline().decode().strip()
        if line == "READY":
            print("Pico is ready!")
            break
        if line:
            print(f"  Pico: {line}")
    else:
        print("Warning: didn't get READY signal, continuing anyway...")

    throttle = 0
    yaw = NEUTRAL
    pitch = NEUTRAL
    roll = NEUTRAL
    step = 100

    def clamp(value):
        return max(0, min(4095, value))

    def send_values():
        cmd = f"{throttle},{yaw},{pitch},{roll}\n"
        ser.write(cmd.encode())
        ser.flush()
        while ser.in_waiting:
            ser.read(ser.in_waiting)
        t_v = throttle / 4095 * 3.3
        y_v = yaw / 4095 * 3.3
        p_v = pitch / 4095 * 3.3
        r_v = roll / 4095 * 3.3
        sys.stdout.write(f"\r  T: {throttle:4d} ({t_v:.2f}V) | Y: {yaw:4d} ({y_v:.2f}V) | P: {pitch:4d} ({p_v:.2f}V) | R: {roll:4d} ({r_v:.2f}V)    ")
        sys.stdout.flush()

    def killswitch():
        nonlocal throttle, yaw, pitch, roll
        throttle = 0
        yaw = NEUTRAL
        pitch = NEUTRAL
        roll = NEUTRAL
        for i in range(5):
            cmd = f"0,{NEUTRAL},{NEUTRAL},{NEUTRAL}\n"
            ser.write(cmd.encode())
            ser.flush()
        print("\n  *** KILLSWITCH ACTIVATED ***")

    def bind_sequence():
        nonlocal throttle
        print("\n  *** BIND (0 -> max -> 0) ***")
        throttle = 0
        print("  ZERO for 2 sec...")
        for i in range(40):
            send_values()
            time.sleep(0.05)
        throttle = 4095
        print("  MAX for 1 sec...")
        for i in range(20):
            send_values()
            time.sleep(0.05)
        throttle = 0
        print("  ZERO for 2 sec...")
        for i in range(40):
            send_values()
            time.sleep(0.05)
        print("  Done. Watch drone lights.")
        send_values()

    def bind_sequence_n():
        nonlocal throttle
        print("\n  *** BIND N (max -> 0) ***")
        throttle = 4095
        print("  MAX for 2 sec...")
        for i in range(40):
            send_values()
            time.sleep(0.05)
        throttle = 0
        print("  ZERO for 2 sec...")
        for i in range(40):
            send_values()
            time.sleep(0.05)
        print("  Done. Watch drone lights.")
        send_values()

    def bind_sequence_p():
        nonlocal throttle
        print("\n  *** BIND P (center -> max -> 0 -> center) ***")
        throttle = 2048
        print("  CENTER for 1 sec...")
        for i in range(20):
            send_values()
            time.sleep(0.05)
        throttle = 4095
        print("  MAX for 0.5 sec...")
        for i in range(10):
            send_values()
            time.sleep(0.05)
        throttle = 0
        print("  ZERO for 0.5 sec...")
        for i in range(10):
            send_values()
            time.sleep(0.05)
        throttle = 2048
        print("  CENTER for 1 sec...")
        for i in range(20):
            send_values()
            time.sleep(0.05)
        print("  Done. Watch drone lights.")
        send_values()

    send_values()

    print("\nControls:")
    print("  W/S              - throttle up/down")
    print("  A/D              - yaw left/right")
    print("  Arrow Up/Down    - pitch forward/back")
    print("  Arrow Left/Right - roll left/right")
    print("  C                - CENTER all (2048)")
    print("  M                - ALL MAX (4095)")
    print("  B                - BIND (0 -> max -> 0)")
    print("  N                - BIND (max -> 0)")
    print("  P                - BIND (center -> max -> 0 -> center)")
    print("  K                - KILLSWITCH")
    print("  Q                - quit")
    print("  +/-              - change step size")
    print(f"\nNeutral: {NEUTRAL} | Step size: {step}")
    print("-" * 60)

    try:
        import tty
        import termios
        import fcntl

        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        old_flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)

        running = True
        while running:
            send_values()

            if select.select([sys.stdin], [], [], 0.1)[0]:
                try:
                    data = sys.stdin.read(10)
                except:
                    data = ''

                if not data:
                    continue

                i = 0
                while i < len(data):
                    char = data[i]

                    if char == '\x1b' and i + 2 < len(data) and data[i+1] == '[':
                        arrow = data[i+2]
                        if arrow == 'A':    # Arrow Up
                            pitch = clamp(pitch + step)
                        elif arrow == 'B':  # Arrow Down
                            pitch = clamp(pitch - step)
                        elif arrow == 'C':  # Arrow Right
                            roll = clamp(roll + step)
                        elif arrow == 'D':  # Arrow Left
                            roll = clamp(roll - step)
                        i += 3
                        continue

                    if char == '\x1b' or char == '[':
                        i += 1
                        continue

                    if char == 'q' or char == 'Q':
                        killswitch()
                        running = False
                    elif char == 'k' or char == 'K':
                        killswitch()
                    elif char == 'c' or char == 'C':
                        throttle = NEUTRAL
                        yaw = NEUTRAL
                        pitch = NEUTRAL
                        roll = NEUTRAL
                        print("\n  All centered to 2048")
                    elif char == 'm' or char == 'M':
                        throttle = 4095
                        yaw = 4095
                        pitch = 4095
                        roll = 4095
                        print("\n  All set to MAX (4095)")
                    elif char == 'b':
                        bind_sequence()
                    elif char == 'n':
                        bind_sequence_n()
                    elif char == 'p':
                        bind_sequence_p()
                    elif char == 'w' or char == 'W':
                        throttle = clamp(throttle + step)
                    elif char == 's' or char == 'S':
                        throttle = clamp(throttle - step)
                    elif char == 'a' or char == 'A':
                        yaw = clamp(yaw - step)
                    elif char == 'd' or char == 'D':
                        yaw = clamp(yaw + step)
                    elif char == '+' or char == '=':
                        step = min(500, step + 50)
                        print(f"\n  Step size: {step}")
                    elif char == '-':
                        step = max(10, step - 50)
                        print(f"\n  Step size: {step}")

                    i += 1

    finally:
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, old_flags)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        killswitch()
        ser.close()
        print("\nDisconnected. Safe defaults sent.")

if __name__ == "__main__":
    main()