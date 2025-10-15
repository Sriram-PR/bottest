import logging
from typing import Optional

import discord
from discord.ext import commands

from config.settings import BOT_COLOR, GENERATION_MAP
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
        self, ctx: commands.Context, pokemon: str, generation: Optional[str] = "gen9"
    ):
        """
        Fetch competitive sets from Smogon

        Args:
            pokemon: Pokemon name (e.g., garchomp, landorus-therian)
            generation: Generation (gen1-gen9, default: gen9)

        Examples:
            .smogon garchomp
            .smogon landorus-therian gen8
            /smogon charizard gen7
        """
        # Defer response for slash commands
        if ctx.interaction:
            await ctx.defer()
        else:
            async with ctx.typing():
                await self._process_smogon_command(ctx, pokemon, generation)
                return

        await self._process_smogon_command(ctx, pokemon, generation)

    async def _process_smogon_command(
        self, ctx: commands.Context, pokemon: str, generation: Optional[str]
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

        # Try multiple tiers to find sets
        tiers_to_try = ["ou", "uu", "ru", "nu", "pu", "ubers", "doublesou", "lc"]
        sets_data = None
        found_tier = None

        for tier in tiers_to_try:
            try:
                sets_data = await self.api_client.get_sets(
                    pokemon, gen_normalized, tier
                )
                if sets_data:
                    found_tier = tier
                    break
            except Exception as e:
                logger.error(f"Error fetching {tier}: {e}")
                continue

        if not sets_data:
            # Pokemon not found in any tier
            embed = create_error_embed(
                "Pokemon Not Found",
                f"No competitive sets found for **{capitalize_pokemon_name(pokemon)}** in **Gen {gen_normalized.replace('gen', '')}**.\n\n"
                f"**Possible reasons:**\n"
                f"• Check spelling (use hyphens for forms: `landorus-therian`)\n"
                f"• Pokemon may not have competitive sets in this generation\n"
                f"• Try a different generation",
            )
            await ctx.send(embed=embed)
            return

        # Create initial embed with first set
        set_names = list(sets_data.keys())
        first_set_name = set_names[0]

        embed = self.create_set_embed(
            pokemon,
            first_set_name,
            sets_data[first_set_name],
            gen_normalized,
            found_tier,
            current_set_index=0,
            total_sets=len(set_names),
        )

        # Create interactive view with dropdowns
        view = SetSelectorView(
            pokemon=pokemon,
            sets_data=sets_data,
            generation=gen_normalized,
            tier=found_tier,
            api_client=self.api_client,
            cog=self,
            timeout=180,
        )

        await ctx.send(embed=embed, view=view)

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
    """View with dropdowns for set and generation selection"""

    def __init__(
        self,
        pokemon: str,
        sets_data: dict,
        generation: str,
        tier: str,
        api_client,
        cog,
        timeout: int = 180,
    ):
        super().__init__(timeout=timeout)
        self.pokemon = pokemon
        self.sets_data = sets_data
        self.generation = generation
        self.tier = tier
        self.api_client = api_client
        self.cog = cog
        self.current_set_index = 0
        self.message: Optional[discord.Message] = None

        # Add dropdowns
        self.add_generation_selector()
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
            for i in range(1, 10)
        ]

        select = discord.ui.Select(
            placeholder="🎮 Select Generation",
            options=options,
            custom_id="generation_select",
            row=0,
        )
        select.callback = self.generation_callback
        self.add_item(select)

    def add_set_selector(self):
        """Add set selector dropdown"""
        set_names = list(self.sets_data.keys())

        # Discord select menu limit is 25 options
        options = []
        for idx, set_name in enumerate(set_names[:25]):
            options.append(
                discord.SelectOption(
                    label=set_name[:100],  # Discord limit
                    value=str(idx),
                    description=f"View {set_name}"[:100],
                    emoji="⚔️",
                    default=(idx == self.current_set_index),
                )
            )

        select = discord.ui.Select(
            placeholder="⚔️ Select Moveset",
            options=options,
            custom_id="set_select",
            row=1,
        )
        select.callback = self.set_callback
        self.add_item(select)

    async def generation_callback(self, interaction: discord.Interaction):
        """Handle generation selection"""
        selected_gen = interaction.data["values"][0]

        await interaction.response.defer()

        # Fetch sets for new generation
        tiers_to_try = ["ou", "uu", "ru", "nu", "pu", "ubers", "doublesou", "lc"]
        new_sets_data = None
        found_tier = None

        for tier in tiers_to_try:
            try:
                new_sets_data = await self.api_client.get_sets(
                    self.pokemon, selected_gen, tier
                )
                if new_sets_data:
                    found_tier = tier
                    break
            except Exception as e:
                logger.error(f"Error fetching {tier}: {e}")
                continue

        if not new_sets_data:
            # No sets found in new generation
            embed = create_error_embed(
                "No Sets Found",
                f"No competitive sets found for **{capitalize_pokemon_name(self.pokemon)}** in **Gen {selected_gen.replace('gen', '')}**.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Update view with new data
        self.generation = selected_gen
        self.tier = found_tier
        self.sets_data = new_sets_data
        self.current_set_index = 0

        # Rebuild view with new dropdowns
        self.clear_items()
        self.add_generation_selector()
        self.add_set_selector()

        # Create new embed
        set_names = list(self.sets_data.keys())
        first_set_name = set_names[0]

        embed = self.cog.create_set_embed(
            self.pokemon,
            first_set_name,
            self.sets_data[first_set_name],
            self.generation,
            self.tier,
            current_set_index=0,
            total_sets=len(set_names),
        )

        await interaction.edit_original_response(embed=embed, view=self)

    async def set_callback(self, interaction: discord.Interaction):
        """Handle set selection"""
        selected_index = int(interaction.data["values"][0])
        self.current_set_index = selected_index

        # Get selected set
        set_names = list(self.sets_data.keys())
        selected_set_name = set_names[selected_index]

        # Update dropdown to show new selection
        self.clear_items()
        self.add_generation_selector()
        self.add_set_selector()

        # Create new embed
        embed = self.cog.create_set_embed(
            self.pokemon,
            selected_set_name,
            self.sets_data[selected_set_name],
            self.generation,
            self.tier,
            current_set_index=selected_index,
            total_sets=len(set_names),
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Disable all items when view times out"""
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


async def setup(bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(Smogon(bot))
    logger.info("Smogon cog loaded successfully")
