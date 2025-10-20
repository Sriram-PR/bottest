import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logger for configuration warnings
logger = logging.getLogger("smogon_bot.config")

# Bot Configuration - Required
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError(
        "❌ DISCORD_TOKEN not found in .env file! Please add it to continue."
    )

# Bot Configuration - Optional
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", ".")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Owner ID (for admin commands)
OWNER_ID = os.getenv("OWNER_ID")
if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        raise ValueError("❌ OWNER_ID must be a valid integer!")
else:
    OWNER_ID = 0
    logger.warning("⚠️  OWNER_ID not set - admin commands will be unavailable")

# Target User ID (for shiny monitoring)
TARGET_USER_ID = os.getenv("TARGET_USER_ID")
if TARGET_USER_ID:
    try:
        TARGET_USER_ID = int(TARGET_USER_ID)
    except ValueError:
        raise ValueError("❌ TARGET_USER_ID must be a valid integer!")
else:
    TARGET_USER_ID = 0
    logger.warning("⚠️  TARGET_USER_ID not set - shiny monitoring will be disabled")

# Shiny Notification Configuration
SHINY_NOTIFICATION_ENABLED = TARGET_USER_ID != 0
SHINY_NOTIFICATION_MESSAGE = os.getenv(
    "SHINY_NOTIFICATION_MESSAGE",
    "🌟 **SHINY POKEMON DETECTED!** 🌟\nA wild shiny has appeared!",
)

# Data Storage
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
SHINY_CONFIG_FILE = DATA_DIR / "shiny_config.json"

# API Configuration
SMOGON_SETS_URL = "https://data.pkmn.cc/sets"
POKEAPI_URL = "https://pokeapi.co/api/v2"

# Bot Settings
BOT_COLOR = 0xFF7BA9
MAX_EMBED_FIELDS = 25
MAX_GENERATION = 9

# Cache Configuration
CACHE_TIMEOUT = 60
MAX_CACHE_SIZE = 200
CACHE_CLEANUP_INTERVAL = 300
CACHE_PERSIST_TO_DISK = True

# Rate Limiting
MAX_CONCURRENT_API_REQUESTS = 5
API_REQUEST_TIMEOUT = 30

# Retry Configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1
RETRY_MAX_DELAY = 10

# Command Cooldowns (seconds)
SMOGON_COMMAND_COOLDOWN = 5
EFFORTVALUE_COMMAND_COOLDOWN = 3
SPRITE_COMMAND_COOLDOWN = 3
DEFAULT_COMMAND_COOLDOWN = 5

# Circuit Breaker Settings
CIRCUIT_BREAKER_ENABLED = True
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Generation Mappings
GENERATION_MAP = {
    "gen1": "gen1",
    "gen2": "gen2",
    "gen3": "gen3",
    "gen4": "gen4",
    "gen5": "gen5",
    "gen6": "gen6",
    "gen7": "gen7",
    "gen8": "gen8",
    "gen9": "gen9",
    "1": "gen1",
    "2": "gen2",
    "3": "gen3",
    "4": "gen4",
    "5": "gen5",
    "6": "gen6",
    "7": "gen7",
    "8": "gen8",
    "9": "gen9",
}

# Tier Mappings
TIER_MAP = {
    "ou": "ou",
    "uu": "uu",
    "ru": "ru",
    "nu": "nu",
    "pu": "pu",
    "zu": "zu",
    "ubers": "ubers",
    "uubers": "uubers",
    "lc": "lc",
    "littlecup": "lc",
    "vgc": "vgc2025regh",
    "vgc2025": "vgc2025regh",
    "doubles": "doublesou",
    "doublesou": "doublesou",
    "dou": "doublesou",
    "1v1": "1v1",
    "monotype": "monotype",
    "ag": "ag",
    "anythinggoes": "ag",
    "cap": "cap",
    "nationaldex": "nationaldex",
    "natdex": "nationaldex",
    "nfe": "nfe",
}

# Comprehensive format lists by generation
# Formats to try when searching (ordered by popularity)
FORMATS_BY_GEN = {
    "gen9": [
        "ou",
        "ubers",
        "nationaldex",
        "uu",
        "doublesou",
        "ru",
        "nu",
        "pu",
        "lc",
        "monotype",
        "1v1",
        "vgc2025regh",
        "zu",
        "cap",
        "ag",
    ],
    "gen8": [
        "ou",
        "ubers",
        "uu",
        "doublesou",
        "ru",
        "nu",
        "pu",
        "lc",
        "monotype",
        "1v1",
        "nationaldex",
        "vgc2021",
        "zu",
        "cap",
        "ag",
    ],
    "gen7": [
        "ou",
        "ubers",
        "uu",
        "doublesou",
        "ru",
        "nu",
        "pu",
        "lc",
        "monotype",
        "1v1",
        "vgc2019",
        "zu",
        "ag",
    ],
    "gen6": [
        "ou",
        "ubers",
        "uu",
        "doublesou",
        "ru",
        "nu",
        "pu",
        "lc",
        "monotype",
        "1v1",
        "vgc2016",
        "ag",
    ],
    "gen5": ["ou", "ubers", "uu", "doublesou", "ru", "nu", "lc", "monotype"],
    "gen4": ["ou", "ubers", "uu", "ru", "nu", "lc"],
    "gen3": ["ou", "ubers", "uu", "nu", "lc"],
    "gen2": ["ou", "ubers", "uu", "nu"],
    "gen1": ["ou", "ubers", "uu"],
}

# Priority formats to check first (most common)
PRIORITY_FORMATS = ["ou", "ubers", "uu", "doublesou"]

# Format display names
FORMAT_NAMES = {
    "ou": "OverUsed",
    "uu": "UnderUsed",
    "ru": "RarelyUsed",
    "nu": "NeverUsed",
    "pu": "PU",
    "zu": "ZeroUsed",
    "lc": "Little Cup",
    "ag": "Anything Goes",
    "ubers": "Ubers",
    "uubers": "UUbers",
    "doublesou": "Doubles OU",
    "1v1": "1v1",
    "monotype": "Monotype",
    "cap": "CAP",
    "nationaldex": "National Dex",
    "vgc2025regh": "VGC 2025 Reg H",
    "vgc2021": "VGC 2021",
    "vgc2019": "VGC 2019",
    "vgc2016": "VGC 2016",
    "nfe": "NFE",
}

# Smogon Dex generation codes
SMOGON_DEX_GENS = {
    "gen1": "rb",
    "gen2": "gs",
    "gen3": "rs",
    "gen4": "dp",
    "gen5": "bw",
    "gen6": "xy",
    "gen7": "sm",
    "gen8": "ss",
    "gen9": "sv",
}

# Type emojis
TYPE_EMOJIS = {
    "normal": "⭐",
    "fire": "🔥",
    "water": "💧",
    "electric": "⚡",
    "grass": "🌿",
    "ice": "❄️",
    "fighting": "🥊",
    "poison": "☠️",
    "ground": "⛰️",
    "flying": "🦅",
    "psychic": "🔮",
    "bug": "🐛",
    "rock": "🪨",
    "ghost": "👻",
    "dragon": "🐉",
    "dark": "🌑",
    "steel": "⚙️",
    "fairy": "🧚",
    "stellar": "✨",
}

# Rate Limiting Configuration
RATE_LIMIT_ENABLED = True
RATE_LIMIT_MAX_REQUESTS = 15  # Max requests per user
RATE_LIMIT_WINDOW = 60  # Time window in seconds (1 minute)
RATE_LIMIT_CLEANUP_INTERVAL = 300  # Cleanup every 5 minutes
