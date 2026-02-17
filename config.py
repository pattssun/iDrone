"""Configuration constants for Hand-Drone simulator."""

# --- Display ---
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS_TARGET = 60

# --- Control mapping ---
CONTROL_DEADZONE_DEG = 3.0       # angles within ±this are treated as zero
CONTROL_EMA_ALPHA = 0.85         # exponential moving average smoothing factor (higher = snappier)
CONTROL_ROLL_SENSITIVITY = 2.0   # multiplier: angle → rate
CONTROL_MAX_ROLL_RATE = 45.0     # degrees per second
CONTROL_PITCH_SENSITIVITY = 2.0  # multiplier: angle → rate
CONTROL_MAX_PITCH_RATE = 45.0    # degrees per second
CONTROL_MAX_RATE_CHANGE = 500.0  # max rate change per second (rate limiting)
CONTROL_MAX_YAW_ANGLE = 45.0    # degrees, clamp range for yaw

# --- Physics ---
PHYSICS_TIMESTEP = 1.0 / 120.0   # fixed timestep (120 Hz)
GRAVITY = 9.81                    # m/s^2
DRONE_MASS = 0.5                  # kg
DRAG_COEFFICIENT = 0.3            # linear drag
MOTOR_RESPONSE_TIME = 0.1        # seconds (first-order lag)
MAX_TILT_ANGLE = 45.0            # degrees, clamp roll/pitch

# --- Altitude hold PID ---
ALTITUDE_HOLD_TARGET = 2.0       # meters
ALTITUDE_PID_KP = 4.0
ALTITUDE_PID_KI = 0.5
ALTITUDE_PID_KD = 2.0
ALTITUDE_PID_MAX_INTEGRAL = 5.0

# --- Landing ---
LANDING_DESCENT_RATE = 0.5      # m/s
LANDING_GROUND_THRESHOLD = 0.05  # meters, consider landed below this

# --- Renderer ---
CHASE_CAM_DISTANCE = 5.0        # meters behind drone
CHASE_CAM_HEIGHT = 2.5           # meters above drone
CHASE_CAM_SMOOTHING = 0.05      # lower = smoother camera follow
GROUND_GRID_SIZE = 50            # grid extends ±this in x and z
GROUND_GRID_SPACING = 1.0       # meters between grid lines
DRONE_ARM_LENGTH = 0.3          # meters, visual arm length
DRONE_PROP_RADIUS = 0.08        # meters, prop circle radius

# --- Dashboard / HUD ---
HUD_FONT_SIZE = 16
HUD_ATTITUDE_RADIUS = 60        # pixels, attitude indicator circle
HUD_ALTITUDE_BAR_WIDTH = 20     # pixels
HUD_ALTITUDE_BAR_HEIGHT = 200   # pixels
HUD_MARGIN = 20                 # pixels from screen edges

# --- Phone gyroscope server ---
PHONE_HTTP_PORT = 8080
PHONE_WS_PORT = 8765
PHONE_TIMEOUT_SECONDS = 2.0  # consider disconnected after this
