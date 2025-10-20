import asyncio
import json
import logging
import re
import shutil
import sys
import time
from typing import Dict, Optional, Set

import discord
from discord.ext import commands

from config.settings import (
    CACHE_TIMEOUT,
    COMMAND_PREFIX,
    DISCORD_TOKEN,
    LOG_LEVEL,
    OWNER_ID,
    RATE_LIMIT_CLEANUP_INTERVAL,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW,
    SHINY_CONFIG_FILE,
    SHINY_NOTIFICATION_MESSAGE,
    TARGET_USER_ID,
)
from utils.rate_limiter import UserRateLimiter

# Setup logging with configurable level
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("smogon_bot")

# Setup intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Shiny detection pattern - checks embed description for "A wild **LvX ★"
SHINY_PATTERN = re.compile(
    r"A\s+wild\s+\*\*Lv\d+\s+★",  # Matches: A wild **Lv4 ★, A wild **Lv50 ★, etc.
    re.UNICODE | re.IGNORECASE,
)

# Pre-built notification message (optimization: built once at startup)
NOTIFICATION_CACHE = SHINY_NOTIFICATION_MESSAGE


class GuildShinyConfig:
    """Configuration for shiny monitoring in a specific guild"""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.channels: Set[int] = set()
        self.embed_channel_id: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage"""
        return {
            "channels": list(self.channels),
            "embed_channel_id": self.embed_channel_id,
        }

    @classmethod
    def from_dict(cls, guild_id: int, data: dict) -> "GuildShinyConfig":
        """Create from dictionary"""
        config = cls(guild_id)
        config.channels = set(data.get("channels", []))
        config.embed_channel_id = data.get("embed_channel_id")
        return config


class SmogonBot(commands.Bot):
    """Custom bot class with proper lifecycle management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time: Optional[float] = None
        # Per-guild configurations
        self.shiny_configs: Dict[int, GuildShinyConfig] = {}
        # Rate limiter cleanup task
        self._rate_limit_cleanup_task: Optional[asyncio.Task] = None

    async def setup_hook(self):
        """Called when bot is starting up - for async initialization"""
        logger.info("Bot setup hook called - performing async initialization")
        self.start_time = time.time()

        # Load per-guild shiny configurations
        self.shiny_configs = load_shiny_configs()

        total_channels = sum(
            len(config.channels) for config in self.shiny_configs.values()
        )
        total_archives = sum(
            1 for config in self.shiny_configs.values() if config.embed_channel_id
        )

        logger.info(f"Loaded configurations for {len(self.shiny_configs)} guild(s)")
        logger.info(f"Total monitored channels: {total_channels}")
        logger.info(f"Guilds with archive channels: {total_archives}")

        # Start rate limiter cleanup task
        if RATE_LIMIT_ENABLED:
            self._rate_limit_cleanup_task = asyncio.create_task(
                self._rate_limit_cleanup_loop()
            )
            logger.info("Started rate limiter cleanup task")

    async def close(self):
        """Override close to ensure proper cleanup of resources"""
        logger.info("Bot shutdown initiated - cleaning up resources")

        # Cancel rate limiter cleanup task
        if self._rate_limit_cleanup_task and not self._rate_limit_cleanup_task.done():
            self._rate_limit_cleanup_task.cancel()
            try:
                await self._rate_limit_cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Cancelled rate limiter cleanup task")

        # Save shiny configurations before shutdown
        save_shiny_configs(self.shiny_configs)
        logger.info("Saved shiny configurations")

        # Close API client sessions from all loaded cogs
        for cog_name, cog in self.cogs.items():
            if hasattr(cog, "api_client"):
                try:
                    await cog.api_client.close()
                    logger.info(f"Closed API client for cog: {cog_name}")
                except Exception as e:
                    logger.error(f"Error closing API client for {cog_name}: {e}")

        logger.info("Cleanup complete - shutting down bot")
        await super().close()

    def get_guild_config(self, guild_id: int) -> GuildShinyConfig:
        """Get or create guild configuration"""
        if guild_id not in self.shiny_configs:
            self.shiny_configs[guild_id] = GuildShinyConfig(guild_id)
            logger.info(f"Created new configuration for guild {guild_id}")
        return self.shiny_configs[guild_id]

    async def _rate_limit_cleanup_loop(self):
        """Background task to periodically clean up rate limiter data"""
        while True:
            try:
                await asyncio.sleep(RATE_LIMIT_CLEANUP_INTERVAL)
                global_rate_limiter.cleanup_expired()
                logger.debug("Rate limiter cleanup completed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}", exc_info=True)


# Create bot instance
bot = SmogonBot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# Initialize global rate limiter
if RATE_LIMIT_ENABLED:
    global_rate_limiter = UserRateLimiter(
        max_requests=RATE_LIMIT_MAX_REQUESTS, window=RATE_LIMIT_WINDOW
    )
    logger.info("Global rate limiter initialized")
else:
    global_rate_limiter = None
    logger.info("Rate limiting disabled")


# Helper functions for shiny configuration persistence
def load_shiny_configs() -> Dict[int, GuildShinyConfig]:
    """Load per-guild shiny configurations from JSON file"""
    try:
        if SHINY_CONFIG_FILE.exists():
            with open(SHINY_CONFIG_FILE, "r") as f:
                data = json.load(f)

                # Handle old format (migrate to new format)
                if "channels" in data and "guilds" not in data:
                    logger.warning(
                        "Old configuration format detected - migrating to per-guild format"
                    )
                    return {}

                # New per-guild format
                guilds_data = data.get("guilds", {})
                configs = {}

                for guild_id_str, guild_data in guilds_data.items():
                    guild_id = int(guild_id_str)
                    configs[guild_id] = GuildShinyConfig.from_dict(guild_id, guild_data)

                return configs

        return {}
    except json.JSONDecodeError as e:
        logger.error(f"❌ Corrupted JSON in shiny config file: {e}")
        logger.warning(
            "Starting with empty config - previous config may be in .bak file"
        )
        return {}
    except Exception as e:
        logger.error(f"Error loading shiny configurations: {e}")
        return {}


def save_shiny_configs(configs: Dict[int, GuildShinyConfig]) -> bool:
    """
    Save per-guild shiny configurations to JSON file with atomic writes and backup

    Uses atomic file operations to prevent data loss on crash/power failure
    """
    try:
        # Ensure data directory exists with proper error handling
        try:
            SHINY_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.error(
                f"❌ No permission to create directory: {SHINY_CONFIG_FILE.parent}"
            )
            return False
        except OSError as e:
            logger.error(f"❌ OS error creating directory: {e}")
            return False

        # Convert to saveable format
        guilds_data = {}
        for guild_id, config in configs.items():
            guilds_data[str(guild_id)] = config.to_dict()

        data = {"guilds": guilds_data}

        # Create backup of existing file before overwriting
        if SHINY_CONFIG_FILE.exists():
            backup_file = SHINY_CONFIG_FILE.with_suffix(".json.bak")
            try:
                shutil.copy2(SHINY_CONFIG_FILE, backup_file)
                logger.debug(f"Created backup: {backup_file}")
            except Exception as e:
                logger.warning(f"Could not create backup: {e}")

        # Atomic write: write to temp file first, then rename
        temp_file = SHINY_CONFIG_FILE.with_suffix(".json.tmp")

        try:
            # Write to temp file
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            # Validate JSON is readable before replacing original
            with open(temp_file, "r") as f:
                json.load(f)

            # Atomic rename (replaces original file)
            temp_file.replace(SHINY_CONFIG_FILE)

            logger.debug("Saved shiny configs atomically")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"❌ Generated invalid JSON: {e}")
            if temp_file.exists():
                temp_file.unlink()
            return False
        except Exception as e:
            logger.error(f"❌ Error during atomic write: {e}")
            if temp_file.exists():
                temp_file.unlink()
            return False

    except Exception as e:
        logger.error(f"Error saving shiny configurations: {e}", exc_info=True)
        return False


async def forward_shiny_to_archive(
    bot: SmogonBot,
    guild_config: GuildShinyConfig,
    first_embed: discord.Embed,
    message: discord.Message,
):
    """
    Forward shiny embed to archive channel (background task)

    This runs independently and doesn't block the main notification.
    Combines embed and jump link into a single API call for efficiency.
    """
    try:
        archive_channel = bot.get_channel(guild_config.embed_channel_id)

        if not archive_channel:
            logger.warning(
                f"Archive channel {guild_config.embed_channel_id} not found "
                f"in {message.guild.name} (may have been deleted)"
            )
            return

        # Create jump link
        jump_link = (
            f"https://discord.com/channels/{message.guild.id}/"
            f"{message.channel.id}/{message.id}"
        )

        # Send embed and jump link in ONE API call (optimization)
        await archive_channel.send(
            content=f"Jump to message: {jump_link}", embed=first_embed
        )

        # Log after successful send (moved to background)
        logger.info(
            f"Forwarded shiny embed to archive channel {archive_channel.name} "
            f"in {message.guild.name}"
        )

    except discord.Forbidden:
        logger.error(
            f"No permission to send in archive channel "
            f"{guild_config.embed_channel_id} in {message.guild.name}"
        )
    except discord.HTTPException as e:
        logger.error(f"HTTP error forwarding to archive: {e}")
    except Exception as e:
        logger.error(f"Unexpected error forwarding to archive: {e}", exc_info=True)


@bot.event
async def on_ready():
    """Called when bot successfully connects to Discord"""
    logger.info(f"{'=' * 50}")
    logger.info(f"{bot.user.name} has connected to Discord!")
    logger.info(f"Bot ID: {bot.user.id}")
    logger.info(f"Connected to {len(bot.guilds)} guild(s)")
    logger.info(f"Discord.py version: {discord.__version__}")

    if TARGET_USER_ID:
        logger.info(f"Monitoring user ID: {TARGET_USER_ID} for shiny Pokemon")

    # Log per-guild statistics
    for guild in bot.guilds:
        if guild.id in bot.shiny_configs:
            config = bot.shiny_configs[guild.id]
            logger.info(
                f"  └─ {guild.name}: {len(config.channels)} monitored channel(s), "
                f"archive: {'✓' if config.embed_channel_id else '✗'}"
            )

    logger.info(f"{'=' * 50}")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        logger.error(f"❌ Failed to sync commands: {e}")

    # Set bot status
    await bot.change_presence(
        activity=discord.Game(name=f"Pokemon Smogon | {COMMAND_PREFIX}smogon")
    )


@bot.event
async def on_message(message: discord.Message):
    """Monitor messages for shiny Pokemon from target user in configured channels"""

    # Ignore bot's own messages
    if message.author.id == bot.user.id:
        return

    # Ignore DMs (no guild)
    if not message.guild:
        await bot.process_commands(message)
        return

    # Wrap shiny detection in try-except to prevent bot crashes
    try:
        # Check if this is a message from the target user
        if TARGET_USER_ID and message.author.id == TARGET_USER_ID:
            # Only show verbose debug logging if LOG_LEVEL is DEBUG
            if LOG_LEVEL.upper() == "DEBUG":
                logger.debug("=" * 60)
                logger.debug("🎯 MESSAGE FROM TARGET USER DETECTED!")
                logger.debug(
                    f"   Author ID: {message.author.id} (Name: {message.author.name})"
                )
                logger.debug(f"   Guild: {message.guild.name} (ID: {message.guild.id})")
                logger.debug(
                    f"   Channel: #{message.channel.name} (ID: {message.channel.id})"
                )
                logger.debug(f"   Message ID: {message.id}")
                logger.debug(f"   Number of embeds: {len(message.embeds)}")

                if message.embeds:
                    for idx, embed in enumerate(message.embeds):
                        logger.debug(f"   --- Embed {idx + 1} ---")

                        # Check description for shiny pattern
                        if embed.description:
                            pattern_match = SHINY_PATTERN.search(embed.description)
                            logger.debug(
                                f"   Description (first 150 chars): '{embed.description[:150]}'"
                            )
                            logger.debug(
                                f"   Pattern match in description: {pattern_match is not None}"
                            )
                            if pattern_match:
                                logger.debug(
                                    f"   ✅ MATCHED! '{pattern_match.group()}'"
                                )

                logger.debug("=" * 60)

            # OPTIMIZED DETECTION LOGIC
            # Early exit if no embeds
            if not message.embeds:
                await bot.process_commands(message)
                return

            first_embed = message.embeds[0]

            # Check description for shiny pattern (before config lookup - optimization)
            if not (
                first_embed.description
                and SHINY_PATTERN.search(first_embed.description)
            ):
                await bot.process_commands(message)
                return

            # Only check config if pattern matched
            guild_config = bot.shiny_configs.get(message.guild.id)

            if guild_config and message.channel.id in guild_config.channels:
                # SHINY DETECTED! Send notification immediately

                # Send notification (PRIORITY - wait for this)
                await message.channel.send(NOTIFICATION_CACHE)

                # Log after sending (optimization: moved after send)
                logger.info(
                    f"✨ Shiny detected in {message.guild.name}#{message.channel.name}! "
                    f"Notification sent"
                )

                # Forward to archive (FIRE-AND-FORGET - don't wait)
                if guild_config.embed_channel_id:
                    asyncio.create_task(
                        forward_shiny_to_archive(
                            bot, guild_config, first_embed, message
                        )
                    )

    except Exception as e:
        # Log error but don't crash the bot
        logger.error(f"Error in shiny detection: {e}", exc_info=True)

    # ALWAYS process commands, even if shiny detection fails
    await bot.process_commands(message)


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Called when bot joins a new guild"""
    logger.info(
        f"✅ Joined guild: {guild.name} (ID: {guild.id}, Members: {guild.member_count})"
    )
    bot.get_guild_config(guild.id)


@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Called when bot is removed from a guild"""
    logger.info(f"❌ Removed from guild: {guild.name} (ID: {guild.id})")
    if guild.id in bot.shiny_configs:
        del bot.shiny_configs[guild.id]
        save_shiny_configs(bot.shiny_configs)
        logger.info(f"Removed configuration for guild {guild.id}")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Global error handler for prefix commands"""

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"⏱️ This command is on cooldown. Try again in **{error.retry_after:.1f}s**",
            delete_after=10,
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            f"❌ Missing required argument: `{error.param.name}`\n"
            f"Use `{COMMAND_PREFIX}help` for command usage.",
            delete_after=15,
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            f"❌ Invalid argument provided!\n"
            f"Use `{COMMAND_PREFIX}help` for command usage.",
            delete_after=15,
        )
    elif isinstance(error, commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await ctx.send(
            f"❌ You don't have permission to use this command!\nRequired: `{perms}`",
            delete_after=15,
        )
    elif isinstance(error, commands.BotMissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await ctx.send(
            f"❌ I don't have the required permissions!\nMissing: `{perms}`",
            delete_after=15,
        )
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(
            "❌ You don't have permission to use this command!", delete_after=15
        )
    else:
        logger.error(
            f"Unexpected error in command '{ctx.command}': {error}", exc_info=error
        )
        await ctx.send(
            "❌ An unexpected error occurred. Please try again later.", delete_after=15
        )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
):
    """Global error handler for slash commands"""

    if interaction.response.is_done():
        send_method = interaction.followup.send
    else:
        send_method = interaction.response.send_message

    if isinstance(error, discord.app_commands.CommandOnCooldown):
        error_message = (
            f"⏱️ This command is on cooldown. Try again in **{error.retry_after:.1f}s**"
        )
    elif isinstance(error, discord.app_commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        error_message = (
            f"❌ You don't have permission to use this command!\nRequired: `{perms}`"
        )
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        perms = ", ".join(error.missing_permissions)
        error_message = f"❌ I don't have the required permissions!\nMissing: `{perms}`"
    else:
        logger.error(f"Unexpected slash command error: {error}", exc_info=error)
        error_message = "❌ An unexpected error occurred. Please try again later."

    try:
        await send_method(error_message, ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to send error message: {e}", exc_info=e)


# ========================================
# CACHE STATS COMMANDS
# ========================================


@bot.tree.command(
    name="cache-stats", description="View API cache statistics (Developer only)"
)
async def cache_stats(interaction: discord.Interaction):
    """View cache performance statistics - Developer only"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    # Get Smogon cog
    smogon_cog = bot.get_cog("Smogon")
    if not smogon_cog or not hasattr(smogon_cog, "api_client"):
        await interaction.response.send_message(
            "❌ API client not available.", ephemeral=True
        )
        return

    api_client = smogon_cog.api_client
    stats = api_client.get_cache_stats()

    # Create embed
    embed = discord.Embed(
        title="📊 API Cache Statistics",
        description="Performance metrics for API caching system",
        color=0x00CED1,
        timestamp=interaction.created_at,
    )

    # Cache size with progress bar
    size_percent = (stats["size"] / stats["max_size"]) * 100
    size_bar = "█" * int(size_percent / 10) + "░" * (10 - int(size_percent / 10))

    embed.add_field(
        name="💾 Cache Size",
        value=(
            f"```{stats['size']:,} / {stats['max_size']:,} entries```\n"
            f"{size_bar} **{size_percent:.1f}%**"
        ),
        inline=False,
    )

    # Hit rate with emoji indicator
    hit_rate_value = float(stats["hit_rate"].rstrip("%"))
    if hit_rate_value >= 70:
        hit_rate_emoji = "🟢"
        performance = "Excellent"
    elif hit_rate_value >= 40:
        hit_rate_emoji = "🟡"
        performance = "Good"
    else:
        hit_rate_emoji = "🔴"
        performance = "Poor"

    embed.add_field(
        name=f"{hit_rate_emoji} Hit Rate",
        value=(
            f"```{stats['hit_rate']}```\n"
            f"**Performance:** {performance}\n"
            f"Hits: {stats['hits']:,} | Misses: {stats['misses']:,}"
        ),
        inline=True,
    )

    # Total requests
    total = stats["hits"] + stats["misses"]
    embed.add_field(
        name="📈 Total Requests", value=f"```{total:,} requests```", inline=True
    )

    # Performance interpretation
    if hit_rate_value >= 70:
        interpretation = (
            "🟢 **Excellent Performance**\n"
            "Cache is working optimally. Most requests are served from cache, "
            "reducing API load significantly."
        )
    elif hit_rate_value >= 40:
        interpretation = (
            "🟡 **Good Performance**\n"
            "Cache is working well, but there's room for improvement. "
            "Consider increasing cache size or timeout."
        )
    else:
        interpretation = (
            "🔴 **Needs Improvement**\n"
            "Low hit rate suggests cache isn't effective. This could be due to:\n"
            "• Users querying diverse Pokemon\n"
            "• Cache timeout too short\n"
            "• Cache size too small"
        )

    embed.add_field(name="💡 Analysis", value=interpretation, inline=False)

    embed.set_footer(text=f"Cache timeout: {CACHE_TIMEOUT}s | Cleaning interval: 5min")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="cache-clear", description="Clear the API cache (Developer only)"
)
async def cache_clear(interaction: discord.Interaction):
    """Manually clear API cache - Developer only"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    smogon_cog = bot.get_cog("Smogon")
    if not smogon_cog or not hasattr(smogon_cog, "api_client"):
        await interaction.response.send_message(
            "❌ API client not available.", ephemeral=True
        )
        return

    # Get stats before clearing
    api_client = smogon_cog.api_client
    old_stats = api_client.get_cache_stats()

    # Clear cache
    api_client.clear_cache()

    embed = discord.Embed(
        title="✅ Cache Cleared",
        description="API cache has been manually cleared",
        color=0x00FF00,
        timestamp=interaction.created_at,
    )

    embed.add_field(
        name="Removed", value=f"{old_stats['size']} cached entries", inline=True
    )

    embed.add_field(name="Previous Hit Rate", value=old_stats["hit_rate"], inline=True)

    embed.add_field(
        name="Total Requests",
        value=f"{old_stats['hits'] + old_stats['misses']:,}",
        inline=True,
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ========================================
# RATE LIMITING COMMANDS
# ========================================


@bot.tree.command(
    name="ratelimit-stats", description="View rate limiter statistics (Developer only)"
)
async def ratelimit_stats(interaction: discord.Interaction):
    """View global rate limiter stats - Developer only"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    if not RATE_LIMIT_ENABLED or not global_rate_limiter:
        await interaction.response.send_message(
            "❌ Rate limiting is disabled.", ephemeral=True
        )
        return

    stats = global_rate_limiter.get_stats()

    embed = discord.Embed(
        title="🚦 Rate Limiter Statistics",
        description="Global rate limiting across all commands and channels",
        color=0xFF6347,
        timestamp=interaction.created_at,
    )

    # Configuration
    embed.add_field(
        name="⚙️ Configuration",
        value=(
            f"**Max Requests:** {stats['max_requests']}\n"
            f"**Time Window:** {stats['window']}s\n"
            f"**Scope:** Per User (Global)"
        ),
        inline=True,
    )

    # Current Status
    limited_emoji = "🔴" if stats["currently_limited"] > 0 else "🟢"
    embed.add_field(
        name=f"{limited_emoji} Current Status",
        value=(
            f"**Users Tracked:** {stats['total_users_tracked']}\n"
            f"**Currently Limited:** {stats['currently_limited']}\n"
            f"**Total Violations:** {stats['total_violations']:,}"
        ),
        inline=True,
    )

    # Performance
    embed.add_field(
        name="📊 Performance",
        value=(
            f"**Total Requests:** {stats['total_requests']:,}\n"
            f"**Blocked:** {stats['total_blocked']:,}\n"
            f"**Block Rate:** {stats['block_rate']}"
        ),
        inline=True,
    )

    # User's personal status
    user_requests, user_remaining, user_reset = global_rate_limiter.get_user_info(
        interaction.user.id
    )

    user_bar = "█" * user_requests + "░" * user_remaining
    user_status_emoji = (
        "🟢" if user_remaining > 5 else "🟡" if user_remaining > 0 else "🔴"
    )

    embed.add_field(
        name=f"{user_status_emoji} Your Status",
        value=(
            f"```{user_bar}```\n"
            f"**Used:** {user_requests}/{stats['max_requests']}\n"
            f"**Remaining:** {user_remaining}\n"
            f"**Resets In:** {user_reset:.1f}s"
        ),
        inline=False,
    )

    # Top violators
    top_violators = global_rate_limiter.get_top_violators(3)
    if top_violators:
        violators_text = []
        for user_id, count in top_violators:
            user = bot.get_user(user_id)
            username = user.name if user else f"Unknown ({user_id})"
            violators_text.append(f"• {username}: {count:,} violations")

        embed.add_field(
            name="⚠️ Top Violators", value="\n".join(violators_text), inline=False
        )

    embed.set_footer(text="Rate limits are per-user across all channels and servers")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="ratelimit-reset", description="Reset rate limit for a user (Developer only)"
)
@discord.app_commands.describe(user="User to reset rate limit for")
async def ratelimit_reset(interaction: discord.Interaction, user: discord.User):
    """Reset rate limit for a specific user - Developer only"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    if not RATE_LIMIT_ENABLED or not global_rate_limiter:
        await interaction.response.send_message(
            "❌ Rate limiting is disabled.", ephemeral=True
        )
        return

    # Get user info before reset
    before_requests, before_remaining, _ = global_rate_limiter.get_user_info(user.id)

    # Reset user
    was_limited = global_rate_limiter.reset_user(user.id)

    if was_limited:
        embed = discord.Embed(
            title="✅ Rate Limit Reset",
            description=f"Rate limit cleared for {user.mention}",
            color=0x00FF00,
            timestamp=interaction.created_at,
        )

        embed.add_field(
            name="Before Reset",
            value=(
                f"Requests: {before_requests}/{global_rate_limiter.max_requests}\n"
                f"Remaining: {before_remaining}"
            ),
            inline=True,
        )

        embed.add_field(
            name="After Reset",
            value=(
                f"Requests: 0/{global_rate_limiter.max_requests}\n"
                f"Remaining: {global_rate_limiter.max_requests}"
            ),
            inline=True,
        )
    else:
        embed = discord.Embed(
            title="ℹ️ No Rate Limit",
            description=f"{user.mention} was not rate limited",
            color=0x3498DB,
            timestamp=interaction.created_at,
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ========================================
# SHINY CHANNEL MANAGEMENT COMMANDS
# ========================================


@bot.tree.command(
    name="shiny-channel",
    description="Manage shiny monitoring channels for this server (Developer only)",
)
@discord.app_commands.describe(
    action="Action to perform",
    channel="Channel to add/remove (leave empty for current channel)",
)
@discord.app_commands.choices(
    action=[
        discord.app_commands.Choice(name="add", value="add"),
        discord.app_commands.Choice(name="remove", value="remove"),
        discord.app_commands.Choice(name="list", value="list"),
        discord.app_commands.Choice(name="clear", value="clear"),
    ]
)
async def shiny_channel(
    interaction: discord.Interaction,
    action: discord.app_commands.Choice[str],
    channel: Optional[discord.TextChannel] = None,
):
    """Manage channels to monitor for shiny Pokemon in this server"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used in a server.", ephemeral=True
        )
        return

    guild_config = bot.get_guild_config(interaction.guild.id)
    action_value = action.value
    target_channel = channel or interaction.channel

    if action_value == "add":
        if target_channel.id in guild_config.channels:
            await interaction.response.send_message(
                f"⚠️ {target_channel.mention} is already being monitored for shinies in this server.",
                ephemeral=True,
            )
        else:
            guild_config.channels.add(target_channel.id)
            save_shiny_configs(bot.shiny_configs)
            await interaction.response.send_message(
                f"✅ Added {target_channel.mention} to shiny monitoring in **{interaction.guild.name}**.\n"
                f"Total channels in this server: {len(guild_config.channels)}",
                ephemeral=True,
            )
            logger.info(
                f"Added channel {target_channel.name} ({target_channel.id}) to shiny monitoring "
                f"in guild {interaction.guild.name} ({interaction.guild.id})"
            )

    elif action_value == "remove":
        if target_channel.id not in guild_config.channels:
            await interaction.response.send_message(
                f"⚠️ {target_channel.mention} is not being monitored for shinies in this server.",
                ephemeral=True,
            )
        else:
            guild_config.channels.remove(target_channel.id)
            save_shiny_configs(bot.shiny_configs)
            await interaction.response.send_message(
                f"✅ Removed {target_channel.mention} from shiny monitoring in **{interaction.guild.name}**.\n"
                f"Total channels in this server: {len(guild_config.channels)}",
                ephemeral=True,
            )
            logger.info(
                f"Removed channel {target_channel.name} ({target_channel.id}) from shiny monitoring "
                f"in guild {interaction.guild.name} ({interaction.guild.id})"
            )

    elif action_value == "list":
        if not guild_config.channels:
            await interaction.response.send_message(
                f"📋 No channels configured for shiny monitoring in **{interaction.guild.name}**.\n"
                "Use `/shiny-channel add` to add channels.",
                ephemeral=True,
            )
        else:
            embed = discord.Embed(
                title=f"🔍 Shiny Monitoring - {interaction.guild.name}",
                description=f"Bot monitors these channels for shinies from target user\nTotal: {len(guild_config.channels)} channel(s)",
                color=0xFFD700,
            )

            channel_list = []
            for channel_id in guild_config.channels:
                channel_obj = bot.get_channel(channel_id)
                if channel_obj:
                    channel_list.append(f"• {channel_obj.mention} (`{channel_id}`)")
                else:
                    channel_list.append(
                        f"• Unknown Channel (`{channel_id}`) - May have been deleted"
                    )

            embed.add_field(
                name="Monitored Channels",
                value="\n".join(channel_list) if channel_list else "None",
                inline=False,
            )

            if TARGET_USER_ID:
                embed.add_field(
                    name="Monitoring User",
                    value=f"<@{TARGET_USER_ID}> (`{TARGET_USER_ID}`)",
                    inline=False,
                )

            if guild_config.embed_channel_id:
                archive_channel = bot.get_channel(guild_config.embed_channel_id)
                if archive_channel:
                    embed.add_field(
                        name="Archive Channel",
                        value=f"{archive_channel.mention} (`{guild_config.embed_channel_id}`)",
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="Archive Channel",
                        value=f"Unknown (`{guild_config.embed_channel_id}`) - May have been deleted",
                        inline=False,
                    )

            embed.set_footer(
                text=f"Configuration is specific to {interaction.guild.name}"
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action_value == "clear":
        count = len(guild_config.channels)
        guild_config.channels.clear()
        save_shiny_configs(bot.shiny_configs)
        await interaction.response.send_message(
            f"✅ Cleared all shiny monitoring channels in **{interaction.guild.name}** ({count} removed).",
            ephemeral=True,
        )
        logger.info(
            f"Cleared all {count} shiny monitoring channels in guild "
            f"{interaction.guild.name} ({interaction.guild.id})"
        )


@bot.tree.command(
    name="shiny-archive",
    description="Manage shiny archive channel for this server (Developer only)",
)
@discord.app_commands.describe(
    action="Action to perform",
    channel="Channel to set as archive (leave empty for current channel)",
)
@discord.app_commands.choices(
    action=[
        discord.app_commands.Choice(name="set", value="set"),
        discord.app_commands.Choice(name="unset", value="unset"),
        discord.app_commands.Choice(name="show", value="show"),
    ]
)
async def shiny_archive(
    interaction: discord.Interaction,
    action: discord.app_commands.Choice[str],
    channel: Optional[discord.TextChannel] = None,
):
    """Manage archive channel where shiny embeds are forwarded in this server"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used in a server.", ephemeral=True
        )
        return

    guild_config = bot.get_guild_config(interaction.guild.id)
    action_value = action.value

    if action_value == "set":
        target_channel = channel or interaction.channel
        guild_config.embed_channel_id = target_channel.id
        save_shiny_configs(bot.shiny_configs)

        await interaction.response.send_message(
            f"✅ Set {target_channel.mention} as the shiny archive channel for **{interaction.guild.name}**.\n"
            f"Shiny embeds will be forwarded here with jump links.",
            ephemeral=True,
        )
        logger.info(
            f"Set shiny archive channel to {target_channel.name} ({target_channel.id}) "
            f"in guild {interaction.guild.name} ({interaction.guild.id})"
        )

    elif action_value == "unset":
        if guild_config.embed_channel_id is None:
            await interaction.response.send_message(
                f"⚠️ No archive channel is currently set for **{interaction.guild.name}**.",
                ephemeral=True,
            )
        else:
            old_channel_id = guild_config.embed_channel_id
            guild_config.embed_channel_id = None
            save_shiny_configs(bot.shiny_configs)

            await interaction.response.send_message(
                f"✅ Removed archive channel from **{interaction.guild.name}** (was: `{old_channel_id}`).\n"
                f"Shiny embeds will no longer be forwarded.",
                ephemeral=True,
            )
            logger.info(
                f"Unset shiny archive channel (was: {old_channel_id}) "
                f"in guild {interaction.guild.name} ({interaction.guild.id})"
            )

    elif action_value == "show":
        if guild_config.embed_channel_id is None:
            await interaction.response.send_message(
                f"📋 No archive channel is currently configured for **{interaction.guild.name}**.\n"
                "Use `/shiny-archive set` to set one.",
                ephemeral=True,
            )
        else:
            archive_channel = bot.get_channel(guild_config.embed_channel_id)

            embed = discord.Embed(
                title=f"📦 Shiny Archive - {interaction.guild.name}",
                description="Shiny embeds are forwarded to this channel",
                color=0xFFD700,
            )

            if archive_channel:
                embed.add_field(
                    name="Archive Channel",
                    value=f"{archive_channel.mention} (`{guild_config.embed_channel_id}`)",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Archive Channel",
                    value=f"Unknown Channel (`{guild_config.embed_channel_id}`) - May have been deleted",
                    inline=False,
                )

            embed.set_footer(
                text=f"Configuration is specific to {interaction.guild.name}"
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)


# ========================================
# GENERAL BOT COMMANDS
# ========================================


@bot.hybrid_command(name="help", description="Show bot commands and usage")
async def help_command(ctx: commands.Context):
    """Display help information"""
    embed = discord.Embed(
        title="🎮 Pokemon Smogon Bot - Help",
        description="Get competitive Pokemon movesets from Smogon University",
        color=0xFF7BA9,
    )

    embed.add_field(
        name="📖 Command Usage",
        value=(
            "**Slash Commands:**\n"
            "`/smogon <pokemon> [generation] [tier]`\n"
            "`/effortvalue <pokemon>`\n"
            "`/sprite <pokemon> [shiny] [generation]`\n"
            "`/dmgcalc`\n"
            "`/ping`\n"
            "`/uptime` (Developer only)\n"
            "`/cache-stats` (Developer only)\n"
            "`/cache-clear` (Developer only)\n"
            "`/ratelimit-stats` (Developer only)\n"
            "`/ratelimit-reset <user>` (Developer only)\n"
            "`/shiny-channel <action>` (Developer only)\n"
            "`/shiny-archive <action>` (Developer only)\n\n"
            "**Note:** Shiny commands are per-server. Each server has its own configuration."
        ),
        inline=False,
    )

    if RATE_LIMIT_ENABLED:
        embed.add_field(
            name="🚦 Rate Limits",
            value=(
                f"**Max Requests:** {RATE_LIMIT_MAX_REQUESTS} per {RATE_LIMIT_WINDOW}s\n"
                "**Scope:** Per user, across all channels\n"
                "**Purpose:** Prevent spam and ensure fair usage"
            ),
            inline=False,
        )

    embed.set_footer(text="Data from Smogon University • Powered by pkmn.cc")

    if isinstance(ctx, commands.Context):
        await ctx.send(embed=embed)
    else:
        await ctx.response.send_message(embed=embed)


@bot.hybrid_command(name="ping", description="Check bot latency and response time")
async def ping(ctx: commands.Context):
    """Check bot's latency"""
    import time

    # WebSocket latency
    ws_latency = round(bot.latency * 1000, 2)

    if ctx.interaction:
        # Slash command - ephemeral
        start_time = time.perf_counter()
        await ctx.defer(ephemeral=True)
        api_latency = round((time.perf_counter() - start_time) * 1000, 2)

        embed = discord.Embed(color=0x2B2D31)
        embed.add_field(
            name="WebSocket Latency", value=f"```{ws_latency} ms```", inline=True
        )
        embed.add_field(
            name="API Response Time", value=f"```{api_latency} ms```", inline=True
        )

        await ctx.send(embed=embed)
    else:
        # Prefix command - normal message
        start_time = time.perf_counter()

        embed = discord.Embed(color=0x2B2D31)
        embed.add_field(
            name="WebSocket Latency", value=f"```{ws_latency} ms```", inline=True
        )
        embed.add_field(name="API Response Time", value="```...```", inline=True)

        msg = await ctx.send(embed=embed)
        api_latency = round((time.perf_counter() - start_time) * 1000, 2)

        # Update with actual API latency
        embed.set_field_at(
            1, name="API Response Time", value=f"```{api_latency} ms```", inline=True
        )
        await msg.edit(embed=embed)


@bot.tree.command(name="uptime", description="Check bot uptime (Developer only)")
async def uptime(interaction: discord.Interaction):
    """Check bot's uptime - Developer only"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    if bot.start_time:
        uptime_seconds = int(time.time() - bot.start_time)

        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_parts = []
        if days > 0:
            uptime_parts.append(f"{days}d")
        if hours > 0:
            uptime_parts.append(f"{hours}h")
        if minutes > 0:
            uptime_parts.append(f"{minutes}m")
        uptime_parts.append(f"{seconds}s")

        uptime_str = " ".join(uptime_parts)

        guild_count = len(bot.guilds)
        user_count = sum(g.member_count for g in bot.guilds if g.member_count)
        latency = round(bot.latency * 1000)

        total_monitored = sum(
            len(config.channels) for config in bot.shiny_configs.values()
        )
        guilds_with_archive = sum(
            1 for config in bot.shiny_configs.values() if config.embed_channel_id
        )

        embed = discord.Embed(
            title="🤖 Bot Status", color=0x00FF00, timestamp=interaction.created_at
        )

        embed.add_field(name="⏰ Uptime", value=uptime_str, inline=True)
        embed.add_field(name="🏓 Latency", value=f"{latency}ms", inline=True)
        embed.add_field(name="🌐 Servers", value=str(guild_count), inline=True)
        embed.add_field(name="👥 Users", value=f"{user_count:,}", inline=True)
        embed.add_field(name="📦 Discord.py", value=discord.__version__, inline=True)
        embed.add_field(
            name="🐍 Python",
            value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            inline=True,
        )

        if TARGET_USER_ID:
            embed.add_field(
                name="🌟 Shiny Monitoring",
                value=(
                    f"User: <@{TARGET_USER_ID}>\n"
                    f"Total Channels: {total_monitored}\n"
                    f"Servers w/ Archive: {guilds_with_archive}/{len(bot.shiny_configs)}"
                ),
                inline=False,
            )

        if RATE_LIMIT_ENABLED and global_rate_limiter:
            rl_stats = global_rate_limiter.get_stats()
            embed.add_field(
                name="🚦 Rate Limiting",
                value=(
                    f"Status: **Enabled**\n"
                    f"Users Tracked: {rl_stats['total_users_tracked']}\n"
                    f"Currently Limited: {rl_stats['currently_limited']}\n"
                    f"Block Rate: {rl_stats['block_rate']}"
                ),
                inline=False,
            )

        embed.set_footer(text=f"Bot Owner: {interaction.user.name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            "⏰ Uptime tracking not available.", ephemeral=True
        )


@bot.tree.command(
    name="debug-message",
    description="Debug the last message from target user (Owner only)",
)
async def debug_message(interaction: discord.Interaction):
    """Debug shiny detection by showing ALL embed fields"""

    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    messages = []
    async for msg in interaction.channel.history(limit=50):
        if msg.author.id == TARGET_USER_ID:
            messages.append(msg)

    if not messages:
        await interaction.followup.send(
            "No messages from target user found!", ephemeral=True
        )
        return

    last_msg = messages[0]

    debug_info = [
        "**Last Message from Target User**",
        f"Author: {last_msg.author.name} (ID: {last_msg.author.id})",
        f"Message ID: {last_msg.id}",
        f"Channel: #{last_msg.channel.name}",
        "",
        f"**Embeds:** {len(last_msg.embeds)}",
    ]

    if last_msg.embeds:
        for idx, embed in enumerate(last_msg.embeds):
            debug_info.append("")
            debug_info.append(f"**═══ Embed {idx + 1} ═══**")

            if embed.title:
                debug_info.append(f"**Title:** `{embed.title}`")

            if embed.author:
                debug_info.append(f"**Author Name:** `{embed.author.name}`")
                debug_info.append(f"**Author Icon:** {embed.author.icon_url or 'None'}")

            if embed.description:
                desc_preview = embed.description[:200]
                debug_info.append(f"**Description:**\n```{desc_preview}```")

            if embed.footer:
                debug_info.append(f"**Footer Text:** `{embed.footer.text}`")

            if embed.image:
                debug_info.append(f"**Image URL:** {embed.image.url[:50]}...")

            debug_info.append("")
            debug_info.append("**🔍 PATTERN TESTS:**")

            # Test description (PRIMARY CHECK)
            if embed.description:
                match = SHINY_PATTERN.search(embed.description)
                debug_info.append(f"**Description match: `{match is not None}`**")
                if match:
                    debug_info.append(f"**✅ SHINY FOUND: `{match.group()}`**")
                else:
                    debug_info.append("❌ No shiny pattern in description")

            # Test title
            if embed.title:
                match = SHINY_PATTERN.search(embed.title)
                debug_info.append(f"Title match: `{match is not None}`")

            # Test author name
            if embed.author and embed.author.name:
                match = SHINY_PATTERN.search(embed.author.name)
                debug_info.append(f"Author.name match: `{match is not None}`")
    else:
        debug_info.append("No embeds!")

    full_text = "\n".join(debug_info)

    # Split into chunks if too long
    if len(full_text) > 2000:
        chunks = [full_text[i : i + 2000] for i in range(0, len(full_text), 2000)]
        for chunk in chunks:
            await interaction.followup.send(chunk, ephemeral=True)
    else:
        await interaction.followup.send(full_text, ephemeral=True)


async def load_cogs():
    """Load all bot cogs"""
    cogs = ["cogs.smogon"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Loaded {cog}")
        except Exception as e:
            logger.error(f"❌ Failed to load {cog}: {e}", exc_info=e)


async def main():
    """Main bot startup function"""
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=e)
        sys.exit(1)
