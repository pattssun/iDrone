"""Configuration constants for Hand-Drone simulator."""

# --- Display ---
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS_TARGET = 60

# --- Webcam ---
WEBCAM_INDEX = 0
WEBCAM_WIDTH = 640
WEBCAM_HEIGHT = 480
WEBCAM_THUMBNAIL_SCALE = 0.3  # fraction of webcam resolution for HUD thumbnail

# --- MediaPipe ---
MP_HAND_MAX_HANDS = 1
MP_HAND_DETECTION_CONFIDENCE = 0.7
MP_HAND_TRACKING_CONFIDENCE = 0.6
MP_FACE_DETECTION_CONFIDENCE = 0.5
MP_FACE_TRACKING_CONFIDENCE = 0.5

# --- Gesture detection ---
# Rock sign: index + pinky extended, middle + ring folded
# "Extended" means tip landmark is above (lower y) its PIP joint
# "Folded" means tip landmark is below (higher y) its PIP joint
GESTURE_HYSTERESIS_FRAMES = 3  # frames of consistent detection before state change

# --- Control mapping ---
CONTROL_DEADZONE_DEG = 5.0       # angles within ±this are treated as zero
CONTROL_EMA_ALPHA = 0.3          # exponential moving average smoothing factor
CONTROL_ROLL_SENSITIVITY = 2.0   # multiplier: angle → rate
CONTROL_PITCH_SENSITIVITY = 2.0
CONTROL_YAW_SENSITIVITY = 1.5
CONTROL_MAX_ROLL_RATE = 45.0     # degrees per second
CONTROL_MAX_PITCH_RATE = 45.0
CONTROL_MAX_YAW_RATE = 90.0
CONTROL_MAX_RATE_CHANGE = 180.0  # max rate change per second (rate limiting)

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
HUD_HEADING_TAPE_WIDTH = 300    # pixels
HUD_MARGIN = 20                 # pixels from screen edges
