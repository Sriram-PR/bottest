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
DISCORD_SELECT_MENU_LIMIT = 25

# API Configuration
DEFAULT_REQUEST_TIMEOUT = 30
MAX_CONCURRENT_REQUESTS = 5
DEFAULT_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1  # seconds
RETRY_MAX_DELAY = 10  # seconds

# Command Configuration
DEFAULT_COMMAND_COOLDOWN = 2  # seconds
COMMAND_COOLDOWN_RATE = 1  # uses per cooldown period

# View/UI Configuration
VIEW_TIMEOUT_SECONDS = 180  # 3 minutes for interactive views
ERROR_MESSAGE_LIFETIME = 15  # seconds before error messages auto-delete
SUCCESS_MESSAGE_LIFETIME = 10  # seconds before success messages auto-delete

# Message History Configuration
MAX_MESSAGE_HISTORY_FOR_DEBUG = 50  # Messages to search when debugging
MAX_MESSAGE_HISTORY_FOR_LOGS = 100  # Messages to check for logging purposes

# Cache Configuration
CACHE_CLEANUP_INTERVAL = 300  # seconds (5 minutes)
CACHE_SAVE_DEBOUNCE_SECONDS = 5  # Debounce frequent saves

# Backup Configuration
SHINY_CONFIG_BACKUP_KEEP = 3  # Number of backup files to keep

# Input Validation
MAX_POKEMON_NAME_LENGTH = 50
MIN_POKEMON_NAME_LENGTH = 1
POKEMON_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9\-\s]+$")

# Circuit Breaker Settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60  # seconds
CIRCUIT_BREAKER_EXPECTED_EXCEPTION = Exception

# Health Check Thresholds
HEALTHY_LATENCY_MS = 200  # Latency below this is considered healthy
WARNING_LATENCY_MS = 500  # Latency above this is warning
CRITICAL_LATENCY_MS = 1000  # Latency above this is critical

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
