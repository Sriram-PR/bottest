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
    COMMAND_PREFIX,
    DISCORD_TOKEN,
    LOG_LEVEL,
    OWNER_ID,
    SHINY_CONFIG_FILE,
    SHINY_NOTIFICATION_MESSAGE,
    TARGET_USER_ID,
)

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

# Shiny detection patterns
SHINY_PATTERN = re.compile(r"Vs\.[\s\u200B]*\u2605", re.UNICODE)
FOOTER_PATTERN = re.compile(r"(.+?)#0\s*\|\s*(.+?)\s*\|")

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
        # Per-channel detection mode tracking
        # "author" = check author.name for "Vs. ★"
        # "footer" = check footer for catch result
        self.shiny_detection_mode: Dict[int, str] = {}

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

    async def close(self):
        """Override close to ensure proper cleanup of resources"""
        logger.info("Bot shutdown initiated - cleaning up resources")

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


# Create bot instance
bot = SmogonBot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)


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
    embed_to_archive: discord.Embed,
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
            content=f"Jump to message: {jump_link}", embed=embed_to_archive
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

                # Show current detection mode for this channel
                current_mode = bot.shiny_detection_mode.get(
                    message.channel.id, "author"
                )
                logger.debug(f"   Detection mode: {current_mode.upper()}")

                if message.embeds:
                    for idx, embed in enumerate(message.embeds):
                        logger.debug(f"   --- Embed {idx + 1} ---")
                        if embed.author and embed.author.name:
                            logger.debug(f"   Author Name: '{embed.author.name}'")
                        if embed.footer and embed.footer.text:
                            logger.debug(f"   Footer Text: '{embed.footer.text}'")

                logger.debug("=" * 60)

            # OPTIMIZED STATE-BASED DETECTION LOGIC
            # Early exit if no embeds
            if not message.embeds:
                await bot.process_commands(message)
                return

            first_embed = message.embeds[0]
            channel_id = message.channel.id

            # Get current detection mode for this channel (default: "author")
            current_mode = bot.shiny_detection_mode.get(channel_id, "author")

            # Only check config if in monitored channel
            guild_config = bot.shiny_configs.get(message.guild.id)

            if not (guild_config and channel_id in guild_config.channels):
                await bot.process_commands(message)
                return

            # STATE-BASED DETECTION (optimization: only check one field at a time)

            if current_mode == "author":
                # AUTHOR MODE: Check author.name for shiny battle start
                if not (first_embed.author and first_embed.author.name):
                    await bot.process_commands(message)
                    return

                # Check for shiny pattern in author.name
                if SHINY_PATTERN.search(first_embed.author.name):
                    # SHINY DETECTED! Send notification immediately
                    await message.channel.send(NOTIFICATION_CACHE)

                    # Log after sending (optimization: moved after send)
                    logger.info(
                        f"✨ Shiny battle detected in {message.guild.name}#{message.channel.name}! "
                        f"Author: {first_embed.author.name}"
                    )

                    # Switch to FOOTER mode for next message
                    bot.shiny_detection_mode[channel_id] = "footer"
                    logger.debug(f"Switched channel {channel_id} to FOOTER mode")

                    # Forward to archive (FIRE-AND-FORGET - don't wait)
                    if guild_config.embed_channel_id:
                        asyncio.create_task(
                            forward_shiny_to_archive(
                                bot, guild_config, first_embed, message
                            )
                        )

            elif current_mode == "footer":
                # FOOTER MODE: Check footer to reset state (no notification/archive)
                if not (first_embed.footer and first_embed.footer.text):
                    await bot.process_commands(message)
                    return

                # Check for catch pattern in footer
                footer_match = FOOTER_PATTERN.search(first_embed.footer.text)

                if footer_match:
                    route_info = footer_match.group(2).strip()

                    # Verify route information exists
                    if "Route " in route_info:
                        # Footer detected - silently switch back to AUTHOR mode
                        bot.shiny_detection_mode[channel_id] = "author"
                        logger.debug(
                            f"Footer detected, switched channel {channel_id} back to AUTHOR mode"
                        )
                    else:
                        # Footer found but no route info, stay in footer mode
                        logger.debug(
                            f"Footer pattern matched but no 'Route ' found in: {route_info}"
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


# Shiny Channel Management Commands (Developer Only)
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
            # Initialize channel to author mode
            bot.shiny_detection_mode[target_channel.id] = "author"
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
            # Remove channel mode tracking
            if target_channel.id in bot.shiny_detection_mode:
                del bot.shiny_detection_mode[target_channel.id]
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
                mode = bot.shiny_detection_mode.get(channel_id, "author")
                if channel_obj:
                    channel_list.append(
                        f"• {channel_obj.mention} (`{channel_id}`) - Mode: {mode}"
                    )
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
        # Clear mode tracking for all channels
        for channel_id in guild_config.channels:
            if channel_id in bot.shiny_detection_mode:
                del bot.shiny_detection_mode[channel_id]
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
            "**Slash Command:**\n"
            "`/smogon <pokemon> [generation] [tier]`\n"
            "`/effortvalue <pokemon>`\n"
            "`/sprite <pokemon> [shiny] [generation]`\n"
            "`/dmgcalc`\n"
            "`/ping`\n"
            "`/uptime` (Developer only)\n"
            "`/shiny-channel <action>` (Developer only)\n"
            "`/shiny-archive <action>` (Developer only)\n\n"
            "**Note:** Shiny commands are per-server. Each server has its own configuration."
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

    # Show current detection mode
    current_mode = bot.shiny_detection_mode.get(interaction.channel.id, "author")

    debug_info = [
        "**Last Message from Target User**",
        f"Author: {last_msg.author.name} (ID: {last_msg.author.id})",
        f"Message ID: {last_msg.id}",
        f"Channel: #{last_msg.channel.name}",
        f"**Current Detection Mode:** {current_mode.upper()}",
        "",
        f"**Embeds:** {len(last_msg.embeds)}",
    ]

    if last_msg.embeds:
        for idx, embed in enumerate(last_msg.embeds):
            debug_info.append("")
            debug_info.append(f"**═══ Embed {idx + 1} ═══**")
            debug_info.append(f"**Title:** `{embed.title}`")

            if embed.author:
                debug_info.append(f"**Author Name:** `{embed.author.name}`")
                pattern_match = SHINY_PATTERN.search(embed.author.name)
                debug_info.append(f"Shiny pattern match: `{pattern_match is not None}`")

            if embed.footer:
                debug_info.append(f"**Footer Text:** `{embed.footer.text}`")
                footer_match = FOOTER_PATTERN.search(embed.footer.text)
                debug_info.append(f"Footer pattern match: `{footer_match is not None}`")
                if footer_match:
                    debug_info.append(f"Username: `{footer_match.group(1)}`")
                    debug_info.append(f"Route info: `{footer_match.group(2)}`")

            if embed.description:
                desc_preview = embed.description[:100]
                debug_info.append(f"**Description:** `{desc_preview}...`")

            if embed.image:
                debug_info.append(f"**Image URL:** {embed.image.url[:50]}...")
    else:
        debug_info.append("No embeds!")

    full_text = "\n".join(debug_info)
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
