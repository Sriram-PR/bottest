import logging
from typing import Dict, Optional

import discord
from discord.ext import commands

from config.settings import BOT_COLOR, GENERATION_MAP, MAX_GENERATION, TIER_MAP
from utils.api_clients import SmogonAPIClient
from utils.helpers import (
    capitalize_pokemon_name,
    create_error_embed,
    format_ability,
    format_evs,
    format_generation_tier,
    format_item,
    format_ivs,
    format_move_list,
    format_nature,
    format_tera_type,
    get_format_display_name,
    truncate_text,
)

logger = logging.getLogger("smogon_bot.smogon")


class Smogon(commands.Cog):
    """Cog for fetching Smogon competitive sets"""

    def __init__(self, bot):
        self.bot = bot
        self.api_client = SmogonAPIClient()

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.bot.loop.create_task(self.api_client.close())
        logger.info("Smogon cog unloaded")

    @commands.hybrid_command(
        name="smogon",
        description="Get competitive movesets from Smogon University",
        aliases=["comp", "set", "sets"],
    )
    async def smogon(
        self,
        ctx: commands.Context,
        pokemon: str,
        generation: str = "gen9",
        tier: Optional[str] = None,
    ):
        """
        Fetch competitive sets from Smogon

        Args:
            pokemon: Pokemon name (e.g., garchomp, landorus-therian)
            generation: Generation (gen1-gen9, default: gen9)
            tier: Tier/format (optional, e.g., ou, uu, ubers)

        Examples:
            .smogon garchomp
            .smogon landorus-therian gen8
            .smogon charizard gen7 uu
            /smogon garchomp gen9 ou
        """
        # Defer response for slash commands
        if ctx.interaction:
            await ctx.defer()
        else:
            async with ctx.typing():
                await self._process_smogon_command(ctx, pokemon, generation, tier)
                return

        await self._process_smogon_command(ctx, pokemon, generation, tier)

    async def _process_smogon_command(
        self,
        ctx: commands.Context,
        pokemon: str,
        generation: str,
        tier: Optional[str],
    ):
        """Process the smogon command logic"""
        # Normalize generation
        gen_input = generation.lower().strip() if generation else "gen9"
        gen_normalized = GENERATION_MAP.get(gen_input, gen_input)

        # Validate generation
        if (
            not gen_normalized.startswith("gen")
            or gen_normalized not in GENERATION_MAP.values()
        ):
            embed = create_error_embed(
                "Invalid Generation",
                f"Generation `{generation}` is not valid.\n"
                f"Use: gen1, gen2, gen3, gen4, gen5, gen6, gen7, gen8, or gen9",
            )
            await ctx.send(embed=embed)
            return

        # Normalize tier if provided
        tier_normalized = None
        if tier:
            tier_input = tier.lower().strip()
            tier_normalized = TIER_MAP.get(tier_input, tier_input)

        # If tier is specified, fetch only that tier
        if tier_normalized:
            try:
                sets_data = await self.api_client.get_sets(
                    pokemon, gen_normalized, tier_normalized
                )

                if not sets_data:
                    # Pokemon not found in specified tier
                    embed = create_error_embed(
                        "Pokemon Not Found",
                        f"No competitive sets found for **{capitalize_pokemon_name(pokemon)}** "
                        f"in **Gen {gen_normalized.replace('gen', '')} {tier_normalized.upper()}**.\n\n"
                        f"**Suggestions:**\n"
                        f"• Check spelling (use hyphens for forms: `landorus-therian`)\n"
                        f"• Try without specifying tier to search all formats\n"
                        f"• Try a different generation",
                    )
                    await ctx.send(embed=embed)
                    return

                # Wrap single tier result in dict format
                all_formats = {tier_normalized: sets_data}

            except Exception as e:
                logger.error(f"Error fetching {tier_normalized}: {e}")
                embed = create_error_embed(
                    "Error",
                    f"Failed to fetch data for **{tier_normalized.upper()}**. The tier may not exist.",
                )
                await ctx.send(embed=embed)
                return
        else:
            # No tier specified - search across all formats
            try:
                all_formats = await self.api_client.find_pokemon_in_generation(
                    pokemon, gen_normalized
                )

                if not all_formats:
                    # Pokemon not found in any tier
                    embed = create_error_embed(
                        "Pokemon Not Found",
                        f"No competitive sets found for **{capitalize_pokemon_name(pokemon)}** "
                        f"in **Gen {gen_normalized.replace('gen', '')}**.\n\n"
                        f"**Possible reasons:**\n"
                        f"• Check spelling (use hyphens for forms: `landorus-therian`)\n"
                        f"• Pokemon may not have competitive sets in this generation\n"
                        f"• Try a different generation",
                    )
                    await ctx.send(embed=embed)
                    return

            except Exception as e:
                logger.error(f"Error searching formats: {e}", exc_info=True)
                embed = create_error_embed(
                    "Error",
                    "An error occurred while searching for the Pokemon. Please try again.",
                )
                await ctx.send(embed=embed)
                return

        # Get first format and first set to display
        first_format = list(all_formats.keys())[0]
        first_format_sets = all_formats[first_format]
        first_set_name = list(first_format_sets.keys())[0]

        # Create initial embed
        embed = self.create_set_embed(
            pokemon,
            first_set_name,
            first_format_sets[first_set_name],
            gen_normalized,
            first_format,
            current_set_index=0,
            total_sets=len(first_format_sets),
        )

        # Create interactive view
        view = SetSelectorView(
            pokemon=pokemon,
            all_formats=all_formats,
            generation=gen_normalized,
            current_format=first_format,
            api_client=self.api_client,
            cog=self,
            timeout=180,
        )

        # Send message and store reference
        message = await ctx.send(embed=embed, view=view)
        view.message = message

    def create_set_embed(
        self,
        pokemon_name: str,
        set_name: str,
        set_info: dict,
        generation: str,
        tier: str,
        current_set_index: int = 0,
        total_sets: int = 1,
    ) -> discord.Embed:
        """
        Create Discord embed for a single moveset

        Args:
            pokemon_name: Pokemon name
            set_name: Name of the set
            set_info: Set data from Smogon
            generation: Generation string
            tier: Tier string
            current_set_index: Current set number (for display)
            total_sets: Total number of sets

        Returns:
            Discord embed
        """
        pokemon_display = capitalize_pokemon_name(pokemon_name)
        format_display = format_generation_tier(generation, tier)

        embed = discord.Embed(
            title=f"{pokemon_display} - {set_name}",
            description=f"**Format:** {format_display}",
            color=BOT_COLOR,
        )

        # Basic info
        level = set_info.get("level", 100)

        # Ability
        ability = format_ability(set_info.get("ability", "Unknown"))
        embed.add_field(name="Ability", value=ability, inline=True)

        # Item
        item = format_item(set_info.get("item", "None"))
        embed.add_field(name="Item", value=item, inline=True)

        # Nature
        nature = format_nature(set_info.get("nature", "Any"))
        embed.add_field(name="Nature", value=nature, inline=True)

        # Moves
        moves = set_info.get("moves", [])
        if moves:
            moves_text = format_move_list(moves)
            embed.add_field(
                name="Moves", value=truncate_text(moves_text, 1024), inline=False
            )

        # EVs
        evs = set_info.get("evs", {})
        if evs:
            ev_text = format_evs(evs)
            embed.add_field(name="EVs", value=ev_text, inline=False)

        # IVs (only if specified and not all 31)
        ivs = set_info.get("ivs", {})
        iv_text = format_ivs(ivs)
        if iv_text:
            embed.add_field(name="IVs", value=iv_text, inline=False)

        # Tera Type (Gen 9+)
        tera_type = set_info.get("teratypes") or set_info.get("teratype")
        if tera_type:
            tera_text = format_tera_type(tera_type)
            if tera_text:
                embed.add_field(name="Tera Type", value=tera_text, inline=True)

        # Footer with metadata
        set_count = f"Set {current_set_index + 1} of {total_sets}"
        embed.set_footer(
            text=f"Data from Smogon University • Level {level} • {set_count}"
        )

        return embed


class SetSelectorView(discord.ui.View):
    """
    View with dropdowns for generation, format, and set selection

    Features:
    - Generation selector (Gen 1-9)
    - Format selector (shows only formats where Pokemon exists)
    - Set selector (shows all sets in selected format, warns if >25)
    """

    def __init__(
        self,
        pokemon: str,
        all_formats: Dict[str, dict],
        generation: str,
        current_format: str,
        api_client,
        cog,
        timeout: int = 180,
    ):
        super().__init__(timeout=timeout)
        self.pokemon = pokemon
        self.all_formats = all_formats  # {tier: {set_name: set_data}}
        self.generation = generation
        self.current_format = current_format
        self.api_client = api_client
        self.cog = cog
        self.current_set_index = 0
        self.message: Optional[discord.Message] = None

        # Add dropdowns
        self.add_generation_selector()
        self.add_format_selector()
        self.add_set_selector()

    def add_generation_selector(self):
        """Add generation selector dropdown"""
        options = [
            discord.SelectOption(
                label=f"Generation {i}",
                value=f"gen{i}",
                description=f"Switch to Gen {i}",
                emoji="🎮",
                default=(f"gen{i}" == self.generation),
            )
            for i in range(1, MAX_GENERATION + 1)
        ]

        select = discord.ui.Select(
            placeholder="🎮 Select Generation",
            options=options,
            custom_id="generation_select",
            row=0,
        )
        select.callback = self.generation_callback
        self.add_item(select)

    def add_format_selector(self):
        """Add format selector dropdown (shows only available formats)"""
        options = []

        for tier in self.all_formats.keys():
            set_count = len(self.all_formats[tier])
            display_name = get_format_display_name(tier, set_count)

            options.append(
                discord.SelectOption(
                    label=display_name[:100],  # Discord limit
                    value=tier,
                    emoji="⚔️",
                    default=(tier == self.current_format),
                )
            )

        select = discord.ui.Select(
            placeholder="📋 Select Format",
            options=options,
            custom_id="format_select",
            row=1,
        )
        select.callback = self.format_callback
        self.add_item(select)

    def add_set_selector(self):
        """Add set selector dropdown"""
        current_sets = self.all_formats[self.current_format]
        set_names = list(current_sets.keys())

        # Discord select menu limit is 25 options
        display_sets = set_names[:25]

        options = []
        for idx, set_name in enumerate(display_sets):
            options.append(
                discord.SelectOption(
                    label=set_name[:100],  # Discord limit
                    value=str(idx),
                    description=f"View {set_name}"[:100],
                    emoji="⚔️",
                    default=(idx == self.current_set_index and idx < 25),
                )
            )

        # Add warning if there are more than 25 sets
        if len(set_names) > 25:
            placeholder = f"⚔️ Select Set (Showing 25/{len(set_names)} sets)"
        else:
            placeholder = "⚔️ Select Moveset"

        select = discord.ui.Select(
            placeholder=placeholder,
            options=options,
            custom_id="set_select",
            row=2,
        )
        select.callback = self.set_callback
        self.add_item(select)

    async def generation_callback(self, interaction: discord.Interaction):
        """Handle generation selection"""
        selected_gen = interaction.data["values"][0]

        await interaction.response.defer()

        # Fetch formats for new generation
        try:
            new_formats = await self.api_client.find_pokemon_in_generation(
                self.pokemon, selected_gen
            )

            if not new_formats:
                # No sets found in new generation
                embed = create_error_embed(
                    "No Sets Found",
                    f"No competitive sets found for **{capitalize_pokemon_name(self.pokemon)}** "
                    f"in **Gen {selected_gen.replace('gen', '')}**.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Update view with new data
            self.generation = selected_gen
            self.all_formats = new_formats
            self.current_format = list(new_formats.keys())[0]
            self.current_set_index = 0

            # Rebuild view with new dropdowns
            self.clear_items()
            self.add_generation_selector()
            self.add_format_selector()
            self.add_set_selector()

            # Create new embed
            first_format_sets = self.all_formats[self.current_format]
            first_set_name = list(first_format_sets.keys())[0]

            embed = self.cog.create_set_embed(
                self.pokemon,
                first_set_name,
                first_format_sets[first_set_name],
                self.generation,
                self.current_format,
                current_set_index=0,
                total_sets=len(first_format_sets),
            )

            await interaction.edit_original_response(embed=embed, view=self)

        except Exception as e:
            logger.error(f"Error in generation callback: {e}", exc_info=True)
            embed = create_error_embed(
                "Error",
                "An error occurred while switching generations. Please try again.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def format_callback(self, interaction: discord.Interaction):
        """Handle format selection"""
        selected_format = interaction.data["values"][0]
        self.current_format = selected_format
        self.current_set_index = 0

        # Update dropdowns
        self.clear_items()
        self.add_generation_selector()
        self.add_format_selector()
        self.add_set_selector()

        # Get first set in new format
        format_sets = self.all_formats[selected_format]
        first_set_name = list(format_sets.keys())[0]

        # Create new embed
        embed = self.cog.create_set_embed(
            self.pokemon,
            first_set_name,
            format_sets[first_set_name],
            self.generation,
            selected_format,
            current_set_index=0,
            total_sets=len(format_sets),
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def set_callback(self, interaction: discord.Interaction):
        """Handle set selection"""
        selected_index = int(interaction.data["values"][0])
        self.current_set_index = selected_index

        # Get selected set
        current_sets = self.all_formats[self.current_format]
        set_names = list(current_sets.keys())
        selected_set_name = set_names[selected_index]

        # Update dropdown to show new selection
        self.clear_items()
        self.add_generation_selector()
        self.add_format_selector()
        self.add_set_selector()

        # Create new embed
        embed = self.cog.create_set_embed(
            self.pokemon,
            selected_set_name,
            current_sets[selected_set_name],
            self.generation,
            self.current_format,
            current_set_index=selected_index,
            total_sets=len(current_sets),
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Remove buttons when view times out"""
        if self.message:
            try:
                await self.message.edit(view=None)
                logger.info("View timed out, buttons removed")
            except Exception as e:
                logger.error(f"Error removing buttons on timeout: {e}")


async def setup(bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(Smogon(bot))
    logger.info("Smogon cog loaded successfully")
