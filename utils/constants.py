"""
Constants for the Pokemon Smogon Bot

Contains Discord limits, API configuration, regex patterns, and error messages.
"""

import re

# Discord Embed Limits
DISCORD_EMBED_TITLE_LIMIT = 256
DISCORD_EMBED_DESCRIPTION_LIMIT = 4096
DISCORD_EMBED_FIELD_VALUE_LIMIT = 1024
DISCORD_EMBED_FIELD_NAME_LIMIT = 256
DISCORD_EMBED_FOOTER_LIMIT = 2048
DISCORD_EMBED_AUTHOR_LIMIT = 256
DISCORD_EMBED_TOTAL_LIMIT = 6000
DISCORD_EMBED_FIELD_COUNT_LIMIT = 25

# API Configuration
DEFAULT_REQUEST_TIMEOUT = 30
MAX_CONCURRENT_REQUESTS = 5
DEFAULT_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1  # seconds
RETRY_MAX_DELAY = 10  # seconds

# Command Configuration
DEFAULT_COMMAND_COOLDOWN = 2  # seconds
COMMAND_COOLDOWN_RATE = 1  # uses per cooldown period

# Input Validation
MAX_POKEMON_NAME_LENGTH = 50
MIN_POKEMON_NAME_LENGTH = 1
POKEMON_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9\-\s]+$")

# Cache Configuration
CACHE_CLEANUP_INTERVAL = 300  # seconds (5 minutes)

# Circuit Breaker Settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60  # seconds
CIRCUIT_BREAKER_EXPECTED_EXCEPTION = Exception

# Error Messages
ERROR_POKEMON_NOT_FOUND = "Pokemon not found. Check spelling and try again."
ERROR_API_UNAVAILABLE = (
    "API service is temporarily unavailable. Please try again later."
)
ERROR_NETWORK_ERROR = "Network error occurred. Please check your connection."
ERROR_INVALID_INPUT = "Invalid input provided. Please check your command."
ERROR_RATE_LIMITED = "You're sending commands too quickly. Please wait a moment."
ERROR_TIMEOUT = "Request timed out. The service may be slow or unavailable."
ERROR_INVALID_GENERATION = "Invalid generation specified. Use gen1 through gen9."
ERROR_INVALID_TIER = "Invalid tier specified. Check available tiers."
ERROR_NO_SETS_FOUND = "No competitive sets found for this Pokemon."

# Success Messages
SUCCESS_CACHE_CLEARED = "Cache cleared successfully."
SUCCESS_COG_RELOADED = "Cog reloaded successfully."

# Info Messages
INFO_SEARCHING = "🔍 Searching for Pokemon..."
INFO_LOADING = "⏳ Loading data..."
INFO_FETCHING = "📡 Fetching from API..."
