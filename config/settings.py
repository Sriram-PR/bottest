import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", ".")
OWNER_ID = int(os.getenv("OWNER_ID", 0))

# Validate required settings
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env file!")

# API Configuration
SMOGON_SETS_URL = "https://data.pkmn.cc/sets"

# Bot Settings
BOT_COLOR = 0xE62129  # Smogon red
CACHE_TIMEOUT = 60  # 60 seconds
MAX_EMBED_FIELDS = 25  # Discord limit
MAX_CACHE_SIZE = 200  # Maximum cache entries (LRU)
MAX_GENERATION = 9  # Current maximum generation

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
