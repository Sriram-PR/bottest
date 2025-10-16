import asyncio
import json
import logging
import re
import sys
import time
from typing import Optional, Set

import discord
from discord.ext import commands

from config.settings import (
    COMMAND_PREFIX,
    DISCORD_TOKEN,
    LOG_LEVEL,
    OWNER_ID,
    SHINY_CHANNELS_FILE,
    SHINY_NOTIFICATION_MESSAGE,
    SHINY_NOTIFICATION_PING_ROLE,
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

# Shiny detection pattern - more robust than hardcoded Unicode
SHINY_PATTERN = re.compile(r"Vs\.[\s\u200B]*★")


class SmogonBot(commands.Bot):
    """Custom bot class with proper lifecycle management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time: Optional[float] = None
        self.shiny_channels: Set[int] = set()  # Store configured channel IDs

    async def setup_hook(self):
        """Called when bot is starting up - for async initialization"""
        logger.info("Bot setup hook called - performing async initialization")
        self.start_time = time.time()

        # Load shiny channels from file
        self.shiny_channels = load_shiny_channels()
        logger.info(f"Loaded {len(self.shiny_channels)} shiny notification channel(s)")

    async def close(self):
        """Override close to ensure proper cleanup of resources"""
        logger.info("Bot shutdown initiated - cleaning up resources")

        # Save shiny channels before shutdown
        save_shiny_channels(self.shiny_channels)
        logger.info("Saved shiny notification channels")

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


# Create bot instance
bot = SmogonBot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)


# Helper functions for shiny channels persistence
def load_shiny_channels() -> Set[int]:
    """Load shiny notification channels from JSON file"""
    try:
        if SHINY_CHANNELS_FILE.exists():
            with open(SHINY_CHANNELS_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("channels", []))
        return set()
    except Exception as e:
        logger.error(f"Error loading shiny channels: {e}")
        return set()


def save_shiny_channels(channels: Set[int]) -> bool:
    """Save shiny notification channels to JSON file"""
    try:
        with open(SHINY_CHANNELS_FILE, "w") as f:
            json.dump({"channels": list(channels)}, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving shiny channels: {e}")
        return False


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
    logger.info(f"Shiny notification channels: {len(bot.shiny_channels)}")
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
    """Monitor messages for shiny Pokemon from target user"""

    # Ignore bot's own messages
    if message.author.id == bot.user.id:
        return

    # Wrap shiny detection in try-except to prevent bot crashes
    try:
        # Check if message is from target user
        if TARGET_USER_ID and message.author.id == TARGET_USER_ID:
            # Check if message has embeds
            if message.embeds:
                first_embed = message.embeds[0]

                # Use regex pattern for more robust matching
                if first_embed.title and SHINY_PATTERN.search(first_embed.title):
                    logger.info(f"✨ Shiny detected! Embed title: {first_embed.title}")

                    # Build notification message from config
                    notification_message = SHINY_NOTIFICATION_MESSAGE

                    # Add role ping if configured
                    if SHINY_NOTIFICATION_PING_ROLE:
                        notification_message = f"<@&{SHINY_NOTIFICATION_PING_ROLE}>\n{notification_message}"

                    # Post notification in all configured channels
                    for channel_id in bot.shiny_channels:
                        try:
                            channel = bot.get_channel(channel_id)
                            if channel:
                                await channel.send(notification_message)
                                logger.info(
                                    f"Posted shiny notification to channel: {channel.name} ({channel_id})"
                                )
                            else:
                                logger.warning(
                                    f"Channel {channel_id} not found (may have been deleted)"
                                )
                        except discord.Forbidden:
                            logger.error(
                                f"No permission to send in channel {channel_id}"
                            )
                        except discord.HTTPException as e:
                            logger.error(
                                f"HTTP error sending to channel {channel_id}: {e}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Unexpected error sending to channel {channel_id}: {e}",
                                exc_info=True,
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


@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Called when bot is removed from a guild"""
    logger.info(f"❌ Removed from guild: {guild.name} (ID: {guild.id})")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Global error handler for prefix commands"""

    # Ignore command not found errors
    if isinstance(error, commands.CommandNotFound):
        return

    # Handle specific error types
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
        # Log unexpected errors
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

    # Determine send method based on interaction state
    if interaction.response.is_done():
        send_method = interaction.followup.send
    else:
        send_method = interaction.response.send_message

    # Handle specific error types
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
    description="Manage shiny notification channels (Developer only)",
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
    """Manage channels for shiny Pokemon notifications"""

    # Check if user is owner
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    action_value = action.value

    # Use provided channel or current channel
    target_channel = channel or interaction.channel

    if action_value == "add":
        if target_channel.id in bot.shiny_channels:
            await interaction.response.send_message(
                f"⚠️ {target_channel.mention} is already in the shiny notification list.",
                ephemeral=True,
            )
        else:
            bot.shiny_channels.add(target_channel.id)
            save_shiny_channels(bot.shiny_channels)
            await interaction.response.send_message(
                f"✅ Added {target_channel.mention} to shiny notification channels.\n"
                f"Total channels: {len(bot.shiny_channels)}",
                ephemeral=True,
            )
            logger.info(
                f"Added channel {target_channel.name} ({target_channel.id}) to shiny notifications"
            )

    elif action_value == "remove":
        if target_channel.id not in bot.shiny_channels:
            await interaction.response.send_message(
                f"⚠️ {target_channel.mention} is not in the shiny notification list.",
                ephemeral=True,
            )
        else:
            bot.shiny_channels.remove(target_channel.id)
            save_shiny_channels(bot.shiny_channels)
            await interaction.response.send_message(
                f"✅ Removed {target_channel.mention} from shiny notification channels.\n"
                f"Total channels: {len(bot.shiny_channels)}",
                ephemeral=True,
            )
            logger.info(
                f"Removed channel {target_channel.name} ({target_channel.id}) from shiny notifications"
            )

    elif action_value == "list":
        if not bot.shiny_channels:
            await interaction.response.send_message(
                "📋 No channels configured for shiny notifications.\n"
                "Use `/shiny-channel add` to add channels.",
                ephemeral=True,
            )
        else:
            embed = discord.Embed(
                title="🌟 Shiny Notification Channels",
                description=f"Total: {len(bot.shiny_channels)} channel(s)",
                color=0xFFD700,
            )

            channel_list = []
            for channel_id in bot.shiny_channels:
                channel_obj = bot.get_channel(channel_id)
                if channel_obj:
                    channel_list.append(f"• {channel_obj.mention} (`{channel_id}`)")
                else:
                    channel_list.append(
                        f"• Unknown Channel (`{channel_id}`) - May have been deleted"
                    )

            embed.add_field(
                name="Configured Channels",
                value="\n".join(channel_list) if channel_list else "None",
                inline=False,
            )

            if TARGET_USER_ID:
                embed.add_field(
                    name="Monitoring User",
                    value=f"<@{TARGET_USER_ID}> (`{TARGET_USER_ID}`)",
                    inline=False,
                )

            embed.set_footer(text="Bot will post shiny alerts in these channels")

            await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action_value == "clear":
        count = len(bot.shiny_channels)
        bot.shiny_channels.clear()
        save_shiny_channels(bot.shiny_channels)
        await interaction.response.send_message(
            f"✅ Cleared all shiny notification channels ({count} removed).",
            ephemeral=True,
        )
        logger.info(f"Cleared all {count} shiny notification channels")


# Help command
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
            f"**Slash Command:**\n"
            f"`/smogon <pokemon> [generation] [tier]`\n"
            f"`/effortvalue <pokemon>`\n"
            f"`/sprite <pokemon> [shiny] [generation]`\n"
            f"`/dmgcalc`\n"
            f"`/ping`\n"
            f"`/uptime` (Developer only)\n"
            f"`/shiny-channel <action>` (Developer only)\n\n"
            f"**Prefix Command:**\n"
            f"`{COMMAND_PREFIX}smogon <pokemon> [generation] [tier]`\n"
            f"`{COMMAND_PREFIX}effortvalue <pokemon>`\n"
            f"`{COMMAND_PREFIX}sprite <pokemon> [shiny] [generation]`\n"
            f"`{COMMAND_PREFIX}dmgcalc`\n"
            f"`{COMMAND_PREFIX}ping`\n\n"
            f"**Examples:**\n"
            f"`/smogon garchomp`\n"
            f"`/effortvalue blissey`\n"
            f"`/sprite charizard yes 1`\n"
            f"`/dmgcalc`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🎯 Parameters",
        value=(
            "**smogon command:**\n"
            "• **pokemon** - Pokemon name (required)\n"
            "• **generation** - gen1 to gen9 (default: gen9)\n"
            "• **tier** - ou, uu, ru, nu, pu, ubers, etc. (optional)\n\n"
            "**effortvalue command:**\n"
            "• **pokemon** - Pokemon name (required)\n\n"
            "**sprite command:**\n"
            "• **pokemon** - Pokemon name (required)\n"
            "• **shiny** - yes/no (default: no)\n"
            "• **generation** - 1 to 9 (default: 9)\n\n"
            "**dmgcalc command:**\n"
            "• No parameters - opens Showdown calculator\n\n"
            "**shiny-channel command:**\n"
            "• **action** - add/remove/list/clear\n"
            "• **channel** - Target channel (optional)"
        ),
        inline=False,
    )

    embed.add_field(
        name="🌐 Supported Tiers",
        value=(
            "OU, UU, RU, NU, PU, ZU\n"
            "Ubers, UUbers\n"
            "LC (Little Cup)\n"
            "VGC, Doubles OU\n"
            "1v1, Monotype, AG (Anything Goes)\n"
            "National Dex, CAP"
        ),
        inline=False,
    )

    embed.add_field(
        name="✨ Features",
        value=(
            "• Interactive format selector\n"
            "• Multiple sets per Pokemon\n"
            "• Automatic tier detection\n"
            "• Generation switcher\n"
            "• EV yield lookup for training\n"
            "• Pokemon sprite viewer (all gens)\n"
            "• Shiny sprite support\n"
            "• Damage calculator link\n"
            "• Direct links to Smogon analysis\n"
            "• Automatic shiny Pokemon alerts"
        ),
        inline=False,
    )

    embed.set_footer(text="Data from Smogon University • Powered by pkmn.cc")

    if isinstance(ctx, commands.Context):
        await ctx.send(embed=embed)
    else:
        await ctx.response.send_message(embed=embed)


# Ping command
@bot.hybrid_command(name="ping", description="Check bot latency and response time")
async def ping(ctx: commands.Context):
    """Check bot's latency"""
    latency = round(bot.latency * 1000)
    message = f"🏓 Pong! **{latency}ms**"

    if ctx.interaction:
        await ctx.send(message, ephemeral=True)
    else:
        await ctx.send(message)


# Uptime command (Developer only, slash command only)
@bot.tree.command(name="uptime", description="Check bot uptime (Developer only)")
async def uptime(interaction: discord.Interaction):
    """Check bot's uptime - Developer only"""

    # Check if user is the owner
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command is only available to the bot owner.", ephemeral=True
        )
        return

    # Calculate uptime
    if bot.start_time:
        uptime_seconds = int(time.time() - bot.start_time)

        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Build uptime string
        uptime_parts = []
        if days > 0:
            uptime_parts.append(f"{days}d")
        if hours > 0:
            uptime_parts.append(f"{hours}h")
        if minutes > 0:
            uptime_parts.append(f"{minutes}m")
        uptime_parts.append(f"{seconds}s")

        uptime_str = " ".join(uptime_parts)

        # Get additional stats
        guild_count = len(bot.guilds)
        user_count = sum(g.member_count for g in bot.guilds if g.member_count)
        latency = round(bot.latency * 1000)

        # Get cache stats if available
        cache_info = ""
        for cog in bot.cogs.values():
            if hasattr(cog, "api_client"):
                try:
                    stats = cog.api_client.get_cache_stats()
                    cache_info = (
                        f"\n📊 **Cache Stats:**\n"
                        f"Size: {stats['size']}/{stats['max_size']}\n"
                        f"Hit Rate: {stats['hit_rate']}\n"
                        f"Hits: {stats['hits']} | Misses: {stats['misses']}"
                    )
                    break
                except:
                    pass

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

        if cache_info:
            embed.add_field(
                name="📊 Cache",
                value=cache_info.split("**Cache Stats:**\n")[1]
                if "**Cache Stats:**" in cache_info
                else cache_info,
                inline=False,
            )

        # Add shiny notification stats
        if TARGET_USER_ID:
            embed.add_field(
                name="🌟 Shiny Alerts",
                value=f"Monitoring: <@{TARGET_USER_ID}>\nChannels: {len(bot.shiny_channels)}",
                inline=False,
            )

        embed.set_footer(text=f"Bot Owner: {interaction.user.name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            "⏰ Uptime tracking not available.", ephemeral=True
        )


# Load cogs
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
