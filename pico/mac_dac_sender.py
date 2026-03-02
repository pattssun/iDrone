"""
Mac DAC Sender - Phase 4
Sends 4 channel values to the Pico over USB serial.

Controls:
  Arrow Up/Down   - increase/decrease throttle
  Arrow Left/Right - adjust yaw
  K               - KILLSWITCH (instant safe defaults)
  Q               - quit

Requires: pip install pyserial
"""

import serial
import serial.tools.list_ports
import time
import sys
import threading

def find_pico_port():
    """Auto-detect the Pico's serial port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Pico shows up as "usbmodem" on Mac
        if "usbmodem" in port.device.lower() or "pico" in port.description.lower():
            return port.device
    # Show available ports if auto-detect fails
    print("Available ports:")
    for port in ports:
        print(f"  {port.device} - {port.description}")
    return None

def main():
    # Find and connect to Pico
    port_name = find_pico_port()
    if port_name is None:
        print("Could not auto-detect Pico. Enter port manually:")
        port_name = input("> ").strip()

    print(f"Connecting to {port_name}...")
    ser = serial.Serial(port_name, 115200, timeout=0.1)
    time.sleep(1)  # Wait for Pico to reset

    # Read until we get READY
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

    # Current values
    throttle = 0
    yaw = 2048
    pitch = 2048
    roll = 2048
    step = 100  # How much each keypress changes the value

    def send_values():
        """Send current values to Pico."""
        cmd = f"{throttle},{yaw},{pitch},{roll}\n"
        ser.write(cmd.encode())
        response = ser.readline().decode().strip()
        # Calculate approximate voltages
        t_v = throttle / 4095 * 3.3
        y_v = yaw / 4095 * 3.3
        p_v = pitch / 4095 * 3.3
        r_v = roll / 4095 * 3.3
        print(f"  Throttle: {throttle:4d} ({t_v:.2f}V) | Yaw: {yaw:4d} ({y_v:.2f}V) | Pitch: {pitch:4d} ({p_v:.2f}V) | Roll: {roll:4d} ({r_v:.2f}V)")

    def killswitch():
        """Immediately send safe defaults."""
        nonlocal throttle, yaw, pitch, roll
        throttle = 0
        yaw = 2048
        pitch = 2048
        roll = 2048
        ser.write(b"KILL\n")
        print("\n  *** KILLSWITCH ACTIVATED ***")

    def clamp(value):
        return max(0, min(4095, value))

    # Send initial safe values
    send_values()

    print("\nControls:")
    print("  W/S     - throttle up/down")
    print("  A/D     - yaw left/right")
    print("  K       - KILLSWITCH")
    print("  Q       - quit")
    print("  +/-     - change step size")
    print(f"\nStep size: {step}")
    print("-" * 60)

    # Simple input loop (works on Mac terminal)
    try:
        import tty
        import termios
        
        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
        
        running = True
        while running:
            char = sys.stdin.read(1)
            
            if char == 'q' or char == 'Q':
                killswitch()
                running = False
            elif char == 'k' or char == 'K':
                killswitch()
            elif char == 'w' or char == 'W':
                throttle = clamp(throttle + step)
                send_values()
            elif char == 's' or char == 'S':
                throttle = clamp(throttle - step)
                send_values()
            elif char == 'a' or char == 'A':
                yaw = clamp(yaw - step)
                send_values()
            elif char == 'd' or char == 'D':
                yaw = clamp(yaw + step)
                send_values()
            elif char == '+' or char == '=':
                step = min(500, step + 50)
                print(f"\r  Step size: {step}    ")
            elif char == '-':
                step = max(10, step - 50)
                print(f"\r  Step size: {step}    ")
        
        # Restore terminal settings
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        
    except ImportError:
        # Fallback for environments without tty support
        print("Using line-input mode. Type commands and press Enter:")
        print("  w/s/a/d = adjust, k = kill, q = quit")
        while True:
            cmd = input("> ").strip().lower()
            if cmd == 'q':
                killswitch()
                break
            elif cmd == 'k':
                killswitch()
            elif cmd == 'w':
                throttle = clamp(throttle + step)
                send_values()
            elif cmd == 's':
                throttle = clamp(throttle - step)
                send_values()
            elif cmd == 'a':
                yaw = clamp(yaw - step)
                send_values()
            elif cmd == 'd':
                yaw = clamp(yaw + step)
                send_values()

    finally:
        killswitch()
        ser.close()
        print("\nDisconnected. Safe defaults sent.")

if __name__ == "__main__":
    main()
