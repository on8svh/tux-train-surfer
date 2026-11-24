"""Game-wide constants. All world units are metres and seconds."""

TITLE = "Tux Train Surfer"
APP_ID = "tux-train-surfer"
FPS = 60

# --- track -----------------------------------------------------------------
LANE_WIDTH = 2.5
LANES = (-1, 0, 1)

# --- player physics ----------------------------------------------------------
GRAVITY = 45.0
JUMP_VELOCITY = 16.7          # apex ~3.1 m
FAST_FALL_VELOCITY = -22.0
LANE_CHANGE_SPEED = 15.0
DUCK_TIME = 0.75
STEP_UP = 0.45                # how far below a roof Tux may be and still land on it
PLAYER_HALF_W = 0.45
PLAYER_HALF_L = 0.35
PLAYER_HEIGHT = 1.45
PLAYER_DUCK_HEIGHT = 0.7
FRONTAL_THRESHOLD = 0.9       # lateral offset below which a hit counts as head-on

# --- obstacles ---------------------------------------------------------------
TRAIN_HEIGHT = 2.4
TRAIN_WIDTH = 2.2
CAR_LENGTH = 12.0
CAR_GAP = 0.9
RAMP_LENGTH = 8.0
BARRIER_WIDTH = 2.1
LOW_BARRIER_HEIGHT = 0.95
HIGH_BARRIER_BOTTOM = 1.0
HIGH_BARRIER_TOP = 3.6

# --- chase -------------------------------------------------------------------
STUMBLE_WINDOW = 6.0          # a second stumble within this time = caught
THIEF_FAR = 14.0
THIEF_NEAR = 2.4

# --- power-ups ---------------------------------------------------------------
MAGNET_TIME = 10.0
MAGNET_RANGE = 22.0
COFFEE_TIME = 12.0            # score multiplier x2
SUPERJUMP_TIME = 12.0
SUPER_JUMP_VELOCITY = 23.2    # apex ~6 m
JETPACK_TIME = 7.0
JETPACK_HEIGHT = 5.6
ZOMBIE_HEIGHT = 1.3

# --- camera / rendering -------------------------------------------------------
VIEW_DISTANCE = 170.0
CAMERA_BACK = 5.5
CAMERA_HEIGHT = 3.6
NEAR_PLANE = 0.8
FOG_START = 45.0

RESOLUTIONS = ((1280, 720), (1600, 900), (1920, 1080), (2560, 1440))
