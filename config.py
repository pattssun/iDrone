"""Configuration constants for iDrone simulator."""

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
CONTROL_YAW_SENSITIVITY = 2.0    # multiplier: angle → rate
CONTROL_MAX_YAW_RATE = 90.0     # degrees per second

# --- Physics ---
PHYSICS_TIMESTEP = 1.0 / 120.0   # fixed timestep (120 Hz)
GRAVITY = 9.81                    # m/s^2
DRONE_MASS = 0.5                  # kg
DRAG_COEFFICIENT = 0.3            # linear drag
MOTOR_RESPONSE_TIME = 0.1        # seconds (first-order lag)
MAX_TILT_ANGLE = 45.0            # degrees, clamp roll/pitch
MOVE_MAX_SPEED = 8.0             # m/s at full tilt (45°)
MOVE_DRAG = 5.0                  # velocity smoothing (higher = snappier)
THROTTLE_MAX_SPEED = 4.0         # m/s vertical at full throttle deflection
THROTTLE_MIN_HEIGHT = 0.1        # meters, ground clamp

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

# =============================================
# DJI Fly-Style Theme
# =============================================

# --- Color palette (pygame 0-255 tuples) ---
THEME_BG = (28, 28, 30)                       # #1c1c1e
THEME_TEXT_PRIMARY = (230, 230, 230)
THEME_TEXT_SECONDARY = (140, 140, 145)
THEME_TEXT_ACCENT = (0, 200, 255)

# --- Color palette (OpenGL 0-1 floats) ---
THEME_CARD_BG = (0.15, 0.15, 0.17, 0.75)
THEME_CARD_BORDER = (0.25, 0.25, 0.28, 0.6)
THEME_STATUS_GREEN = (0.18, 0.82, 0.35)
THEME_STATUS_RED = (1.0, 0.27, 0.23)
THEME_STATUS_ORANGE = (1.0, 0.62, 0.04)
THEME_STATUS_BLUE = (0.04, 0.52, 1.0)

# --- Sky gradient (3-band, OpenGL 0-1 floats) ---
SKY_TOP_COLOR = (0.38, 0.55, 0.78)
SKY_MID_COLOR = (0.62, 0.74, 0.88)
SKY_BOTTOM_COLOR = (0.78, 0.82, 0.87)

# --- Ground surface ---
GROUND_COLOR = (0.18, 0.20, 0.18)
GROUND_GRID_COLOR = (0.30, 0.32, 0.30, 0.35)
GROUND_GRID_ACCENT = (0.40, 0.42, 0.38, 0.5)

# --- Drone model ---
DRONE_BODY_COLOR = (0.25, 0.25, 0.28)
DRONE_ARM_WIDTH = 0.03                         # meters, half-width of arm quads
DRONE_PROP_DISC_ALPHA = 0.18
DRONE_SHADOW_RADIUS = 0.35                     # meters
DRONE_SHADOW_ALPHA = 0.22

# --- HUD layout (DJI-style) ---
HUD_FONT_LARGE = 28
HUD_FONT_MEDIUM = 18
HUD_FONT_SMALL = 14
HUD_ATTITUDE_RADIUS_NEW = 45                   # pixels
HUD_COMPASS_HEIGHT = 28                        # pixels tall
HUD_COMPASS_WIDTH_FRAC = 0.35                  # fraction of screen width
HUD_ALT_CARD_W = 180
HUD_ALT_CARD_H = 70
HUD_SPEED_CARD_W = 120
HUD_SPEED_CARD_H = 50
HUD_STATUS_DOT_RADIUS = 5

# --- Obstacles ---
OBSTACLE_DRONE_RADIUS = 0.4          # collision sphere radius for drone
OBSTACLE_BOUNCE_FACTOR = 0.3         # velocity reflection multiplier
OBSTACLE_PUSH_EPSILON = 0.01         # extra push-out to prevent sticking

OBSTACLE_BUILDING_COLOR = (0.22, 0.22, 0.25)
OBSTACLE_BUILDING_ROOF_COLOR = (0.28, 0.28, 0.32)
OBSTACLE_BUILDING_EDGE_COLOR = (0.35, 0.35, 0.40, 0.6)
OBSTACLE_TREE_TRUNK_COLOR = (0.30, 0.20, 0.12)
OBSTACLE_TREE_CANOPY_COLOR = (0.15, 0.35, 0.15)
OBSTACLE_POLE_COLOR = (0.50, 0.50, 0.52)
OBSTACLE_POLE_LIGHT_COLOR = (1.0, 0.3, 0.2)
OBSTACLE_HOOP_COLOR = (1.0, 0.62, 0.04)
OBSTACLE_SHADOW_ALPHA = 0.15
