import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", ".")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
TARGET_USER_ID = int(os.getenv("TARGET_USER_ID", 0))
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")  # production or development

# Validate required settings
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env file!")

# Data Storage
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)  # Create data directory if it doesn't exist
SHINY_CHANNELS_FILE = DATA_DIR / "shiny_channels.json"

# API Configuration
SMOGON_SETS_URL = "https://data.pkmn.cc/sets"
POKEAPI_URL = "https://pokeapi.co/api/v2"

# Bot Settings
BOT_COLOR = 0xFF7BA9  # Smogon red
MAX_EMBED_FIELDS = 25  # Discord limit
MAX_GENERATION = 9  # Current maximum generation

# Cache Configuration
CACHE_TIMEOUT = 60  # 60 seconds
MAX_CACHE_SIZE = 200  # Maximum cache entries (LRU)
CACHE_CLEANUP_INTERVAL = 300  # Clean expired cache every 5 minutes

# Rate Limiting
MAX_CONCURRENT_API_REQUESTS = 5  # Maximum parallel API calls
API_REQUEST_TIMEOUT = 30  # Seconds before timeout

# Retry Configuration
MAX_RETRY_ATTEMPTS = 3  # Number of retries for failed API calls
RETRY_BASE_DELAY = 1  # Base delay for exponential backoff (seconds)
RETRY_MAX_DELAY = 10  # Maximum retry delay (seconds)

# Command Cooldowns (seconds)
SMOGON_COMMAND_COOLDOWN = 5
EFFORTVALUE_COMMAND_COOLDOWN = 3
SPRITE_COMMAND_COOLDOWN = 3
DEFAULT_COMMAND_COOLDOWN = 5

# Circuit Breaker Settings
CIRCUIT_BREAKER_ENABLED = True
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60  # seconds

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG, INFO, WARNING, ERROR

# Generation and Tier Mappings
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

# Emoji mappings for types
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
