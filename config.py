"""
ProtoCube Configuration File
Centralized configuration parameters, toggles, durations, and system constants.
"""

import sys
from pathlib import Path

#path
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

IDLE_IMAGE_DIR = ASSETS_DIR / "image" / "idle"
CLICK_IMAGE_DIR = ASSETS_DIR / "image" / "click"
HURT_IMAGE_DIR = ASSETS_DIR / "image" / "hurt"
TALK_IMAGE_DIR = ASSETS_DIR / "image" / "talk"
SINGING_IMAGE_DIR = ASSETS_DIR / "image" / "singing"
LISTENING_IMAGE_DIR = ASSETS_DIR / "image" / "listening"
THINKING_IMAGE_DIR = ASSETS_DIR / "image" / "thinking"
EAT_IMAGE_DIR = ASSETS_DIR / "image" / "eat"
LONELY_IMAGE_DIR = ASSETS_DIR / "image" / "lonely"
CRYING_IMAGE_DIR = ASSETS_DIR / "image" / "crying"

CLICK_SOUND_DIR = ASSETS_DIR / "sfx" / "click"
TALK_SOUND_DIR = ASSETS_DIR / "sfx" / "talk"
HURT_SOUND_DIR = ASSETS_DIR / "sfx" / "hurt"
HIT_WALL_SOUND_DIR = ASSETS_DIR / "sfx" / "hit_wall"
DEAD_SOUND_DIR = ASSETS_DIR / "sfx" / "dead"
SING_SOUND_DIR = ASSETS_DIR / "sfx" / "sing"
EAT_SOUND_DIR = ASSETS_DIR / "sfx" / "eat"
SPAWN_SOUND_DIR = ASSETS_DIR / "sfx" / "spawn"
CRYING_SOUND_DIR = ASSETS_DIR / "sfx" / "crying"

#window
PET_SIZE = 100
ENABLE_WINDOW_SITTING = True
WINDOW_SURFACE_SCAN_INTERVAL_MS = 250 #enumerate windows at 4 Hz only while moving.
WINDOW_SIT_TRACK_INTERVAL_MS = 100 #track only the landed-on window at 10 Hz.
WINDOW_SIT_MOVING_TRACK_INTERVAL_MS = 33 #temporarily follow a moving window smoothly.
WINDOW_SIT_MOTION_HOLD_MS = 350
WINDOW_SIT_MIN_WIDTH = 200
WINDOW_SIT_MIN_HEIGHT = 200
WINDOW_SIT_EDGE_MARGIN = 15
WINDOW_SIT_LANDING_TOLERANCE = 50
ENABLE_CLICK_JUMP = True #bounce up when clicked

#animation durations
CLICK_REACTION_DURATION_MS = 300 #click reaction display time
HURT_REACTION_DURATION_MS = 500 #hurt reaction display time
SINGING_FRAME_INTERVAL_MS = 500 #default singing frame interval
THINKING_FRAME_INTERVAL_MS = 300 #thinking frame interval
EATING_FRAME_INTERVAL_MS = 250 #eating animation frame interval
EATING_DURATION_MS = 3000 #eating reaction duration

#spawn
ENABLE_SPAWN_MESSAGE = True
SPAWN_MESSAGE_TEXT = "hello world...?"
SPAWN_MESSAGE_DURATION_MS = 4000
SPAWN_START_DELAY_MS = 100 

#audio and sound
CLICK_SOUND_VOICES = 4
CLICK_SOUND_VOLUME = 400
CLICK_SOUND_LISTENING_FALLBACK_MS = 750
CLICK_SOUND_LISTENING_TAIL_MS = 150
HIT_WALL_SOUND_VOICES = 2
HIT_WALL_SOUND_VOLUME = 400
HURT_SOUND_VOICES = 2
HURT_SOUND_VOLUME = 400
IMPACT_SOUND_COOLDOWN_MS = 250
HURT_SOUND_LISTENING_FALLBACK_MS = 1_000
HURT_SOUND_LISTENING_TAIL_MS = 150
ENABLE_TALK_SOUND = True
DEAD_SOUND_FALLBACK_DURATION_MS = 1_500
DEAD_SOUND_MAX_DURATION_MS = 15_000
SUPPORTED_IDLE_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
SUPPORTED_SOUND_EXTENSIONS = {".mp3", ".wav"}
SUPPORTED_TEXT_EXTENSIONS = {
    ".ahk", ".bat", ".c", ".cfg", ".cpp", ".cs", ".css", ".csv",
    ".go", ".h", ".hpp", ".html", ".ini", ".java", ".js", ".json",
    ".jsx", ".log", ".md", ".ps1", ".py", ".rs", ".sql", ".toml",
    ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
MAX_DROPPED_FILE_BYTES = 64 * 1_024

#physics
CLICK_JUMP_IMPULSE = 300.0
CLICK_JUMP_COOLDOWN_MS = 500
PHYSICS_INTERVAL_MS = 16
GRAVITY = 1_850.0
BOUNCE = 0.5
WALL_BOUNCE = 0.8
HURT_IMPACT_THRESHOLD = 1500.0  #Speed threshold in px/s to trigger hurt image
MAX_THROW_SPEED = 2_400.0

#idle mood phases
ENABLE_IDLE_MOOD_PHASES = True
IDLE_MOOD_DISABLED_BRAIN_MODES = {"deep"} #multi mode assign support
IDLE_MOOD_DEFAULT_FRAME_INTERVAL_MS = 350
IDLE_MOOD_SOUND_VOLUME = 700
IDLE_PHASES = [
    {
        "name": "Happy / Content",
        "inactivity_ms": 0,
        "chatter_interval_ms": None,
        "image_dir": IDLE_IMAGE_DIR,
        "fallback_image_dir": IDLE_IMAGE_DIR,
        "animate": False,
        "sound_dir": None,
        "loop_sound": False,
        "talk_sound": False,
        "system_audio_listening": True,
        "bubble_duration_ms": 4_000,
        "lines": [],
    },
    {
        "name": "Casual Chatter",
        "inactivity_ms": 10000, #2 * 60_000,
        "chatter_interval_ms": (10000, 20000),
        "image_dir": IDLE_IMAGE_DIR,
        "fallback_image_dir": IDLE_IMAGE_DIR,
        "animate": False,
        "sound_dir": None,
        "loop_sound": False,
        "talk_sound": True,
        "system_audio_listening": True,
        "bubble_duration_ms": 5_000,
        "lines": [
            "Just sitting here watching you work [._.]",
            "Did you remember to stay hydrated? [^w^]",
            "Whatcha working on over there? [o_o]",
        ],
    },
    {
        "name": "Lonely",
        "inactivity_ms": 60000,#5 * 60_000,
        "chatter_interval_ms": (10000, 20000),
        "image_dir": LONELY_IMAGE_DIR,
        "fallback_image_dir": HURT_IMAGE_DIR,
        "animate": True,
        "frame_interval_ms": 500,
        "sound_dir": None,
        "loop_sound": False,
        "talk_sound": True,
        "system_audio_listening": False,
        "bubble_duration_ms": 6_000,
        "lines": [
            "Are you still there...? [u_u]",
            "Don't forget about me... [._.]",
            "It got awfully quiet over here [u_u]",
        ],
    },
    {
        "name": "Crying",
        "inactivity_ms": 2 *60000, #10 * 60_000,
        "chatter_interval_ms": (10000, 20000),
        "image_dir": CRYING_IMAGE_DIR,
        "fallback_image_dir": HURT_IMAGE_DIR,
        "animate": True,
        "frame_interval_ms": 300,
        "sound_dir": CRYING_SOUND_DIR,
        "loop_sound": True,
        "talk_sound": False,  # Avoid layering word sounds over looping crying.
        "system_audio_listening": False,
        "bubble_duration_ms": 7_000,
        "lines": [
            "Waaaaah! Don't leave me alone! 😭 [T_T]",
            "I'm so lonely... [q_q]",
            "Come back and boop me already! [T_T]",
        ],
    },
]

# Adaptive system-audio listening. Quiet mode performs only four peak checks per
# second; active mode temporarily increases sampling for responsive animation.
ENABLE_LISTENING_ANIMATION = True
LISTENING_IDLE_POLL_INTERVAL_MS = 250
LISTENING_ACTIVE_POLL_INTERVAL_MS = 50
LISTENING_LOUDNESS_THRESHOLD = 0.015
LISTENING_RELEASE_THRESHOLD = 0.007
LISTENING_RELEASE_DELAY_MS = 800
LISTENING_FRAME_MIN_INTERVAL_MS = 80
LISTENING_FRAME_MAX_INTERVAL_MS = 300

#hotkeys
GLOBAL_HOTKEY_ID = 0x5052
ACTIVATE_HOTKEY_ID = 0x5054
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
VK_F = 0x46
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
