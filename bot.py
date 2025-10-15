import asyncio
import logging
import sys

import discord
from discord.ext import commands

from config.settings import COMMAND_PREFIX, DISCORD_TOKEN

# Setup logging
logging.basicConfig(
    level=logging.INFO,
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

# Create bot instance
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready():
    logger.info(f"{bot.user.name} has connected to Discord!")
    logger.info(f"Bot ID: {bot.user.id}")
    logger.info(f"Connected to {len(bot.guilds)} guild(s)")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

    # Set bot status
    await bot.change_presence(
        activity=discord.Game(name=f"Pokemon | {COMMAND_PREFIX}smogon")
    )


@bot.event
async def on_close():
    """Cleanup when bot is shutting down"""
    logger.info("Bot shutting down, cleaning up resources...")

    # Close API client sessions from all loaded cogs
    for cog in bot.cogs.values():
        if hasattr(cog, "api_client"):
            try:
                await cog.api_client.close()
            except Exception as e:
                logger.error(f"Error closing API client: {e}")

    logger.info("Cleanup complete")


@bot.event
async def on_guild_join(guild):
    logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")


@bot.event
async def on_guild_remove(guild):
    logger.info(f"Removed from guild: {guild.name} (ID: {guild.id})")


@bot.event
async def on_command_error(ctx, error):
    """Global error handler for prefix commands"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument provided!")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have the required permissions!")
    else:
        logger.error(f"Command error: {error}", exc_info=error)
        await ctx.send(f"❌ An error occurred: {str(error)}")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    """Global error handler for slash commands"""
    if interaction.response.is_done():
        send_method = interaction.followup.send
    else:
        send_method = interaction.response.send_message

    error_message = f"❌ An error occurred: {str(error)}"
    try:
        await send_method(error_message, ephemeral=True)
    except:
        logger.error(f"Failed to send error message: {error}", exc_info=error)


# Help command
@bot.hybrid_command(name="help", description="Show bot commands and usage")
async def help_command(ctx):
    """Display help information"""
    embed = discord.Embed(
        title="🎮 Pokemon Smogon Bot - Help",
        description="Get competitive Pokemon movesets from Smogon University",
        color=0xE62129,
    )

    embed.add_field(
        name="📖 Command Usage",
        value=(
            f"**Slash Command:**\n"
            f"`/smogon <pokemon> [generation] [tier]`\n\n"
            f"**Prefix Command:**\n"
            f"`{COMMAND_PREFIX}smogon <pokemon> [generation] [tier]`\n\n"
            f"**Examples:**\n"
            f"`/smogon garchomp`\n"
            f"`/smogon landorus-therian gen8`\n"
            f"`/smogon charizard gen7 uu`\n"
            f"`{COMMAND_PREFIX}smogon garchomp gen9 ou`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🎯 Parameters",
        value=(
            "**pokemon** - Pokemon name (required)\n"
            "**generation** - gen1 to gen9 (default: gen9)\n"
            "**tier** - ou, uu, ru, nu, pu, ubers, etc. (optional)\n"
            "• If tier not specified, bot will search all tiers"
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
            "• Generation switcher"
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
async def ping(ctx):
    """Check bot's latency"""
    # Calculate latency in milliseconds
    latency = round(bot.latency * 1000)

    # Simple message
    message = f"Pong! (**{latency}ms** to gateway)"

    # Send as ephemeral for slash commands, normal for prefix
    if isinstance(ctx, commands.Context):
        # Prefix command - can't be ephemeral
        await ctx.send(message)
    else:
        # Slash command - ephemeral (only you can see)
        await ctx.response.send_message(message, ephemeral=True)


# Load cogs
async def load_cogs():
    """Load all bot cogs"""
    cogs = ["cogs.smogon"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Loaded {cog}")
        except Exception as e:
            logger.error(f"❌ Failed to load {cog}: {e}")


async def main():
    """Main bot startup function"""
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=e)
