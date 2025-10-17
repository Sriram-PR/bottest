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
SHINY_NOTIFICATION_PING_ROLE = os.getenv("SHINY_NOTIFICATION_PING_ROLE", "")

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
FORMAT_CACHE_TIMEOUT = 86400  # Cache discovered formats for 24 hours

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

# ============================================================================
# COMPREHENSIVE FORMAT LIST
# ============================================================================
# Instead of maintaining per-generation lists, we have ONE comprehensive list
# of ALL possible formats. The API will tell us which ones actually exist.
# This automatically handles new formats without code changes!
# ============================================================================

COMPREHENSIVE_FORMAT_LIST = [
    # Standard Tiers (priority order - most common first)
    "ou",  # OverUsed - Most popular
    "ubers",  # Ubers - Legendaries
    "nationaldex",  # National Dex - All Pokemon
    "uu",  # UnderUsed
    "doublesou",  # Doubles OU
    "ru",  # RarelyUsed
    "nu",  # NeverUsed
    "pu",  # PU
    "zu",  # ZeroUsed
    # Special Formats
    "lc",  # Little Cup
    "monotype",  # Monotype
    "1v1",  # 1v1
    "ag",  # Anything Goes
    "cap",  # Create-A-Pokemon
    # VGC Formats (by year)
    "vgc2025regh",
    "vgc2025regg",
    "vgc2025regf",
    "vgc2024regi",
    "vgc2024regh",
    "vgc2024regg",
    "vgc2024regf",
    "vgc2023",
    "vgc2022",
    "vgc2021",
    "vgc2020",
    "vgc2019",
    "vgc2018",
    "vgc2017",
    "vgc2016",
    "vgc2015",
    "vgc2014",
    "vgc2013",
    "vgc2012",
    "vgc2011",
    # Battle Stadium Singles (BSS)
    "battlestadiumsingles",
    "bss",
    # Other Competitive Formats
    "uubers",  # UU Ubers (Gen 8)
    "nfe",  # Not Fully Evolved
    "lcuu",  # Little Cup UU
    "doublesuu",  # Doubles UU
    "doublesru",  # Doubles RU
    "doublesnu",  # Doubles NU
    "doubleslc",  # Doubles LC
    "triples",  # Triples (Gen 6-7)
    "rotation",  # Rotation (Gen 5)
    # Metagames
    "balancedhackmons",  # Balanced Hackmons
    "mixandmega",  # Mix and Mega
    "almostanyability",  # Almost Any Ability
    "stabmons",  # STABmons
    "ndag",  # National Dex AG
    "godlygift",  # Godly Gift
    "purehackmons",  # Pure Hackmons
    # Past Gen Specific
    "battlespot",  # Battle Spot (Gen 6-7)
    "battlespotsingles",  # Battle Spot Singles
    "battlespotdoubles",  # Battle Spot Doubles
    "battlespottriples",  # Battle Spot Triples
    # Misc
    "uber",  # Alternate spelling
    "pu2",  # PU alternative
    "customgame",  # Custom Game
]

# Priority formats to check first (most common)
PRIORITY_FORMATS = [
    "ou",
    "ubers",
    "nationaldex",
    "uu",
    "doublesou",
]

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
    "vgc2025regg": "VGC 2025 Reg G",
    "vgc2024regi": "VGC 2024 Reg I",
    "vgc2021": "VGC 2021",
    "vgc2019": "VGC 2019",
    "vgc2016": "VGC 2016",
    "nfe": "NFE",
    "battlestadiumsingles": "Battle Stadium Singles",
    "balancedhackmons": "Balanced Hackmons",
    "mixandmega": "Mix and Mega",
    "almostanyability": "Almost Any Ability",
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
