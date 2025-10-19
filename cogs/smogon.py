import logging
from typing import Dict, Optional

import discord
from discord.ext import commands

from config.settings import (
    BOT_COLOR,
    EFFORTVALUE_COMMAND_COOLDOWN,
    MAX_GENERATION,
    SMOGON_COMMAND_COOLDOWN,
    SPRITE_COMMAND_COOLDOWN,
)
from utils.api_clients import SmogonAPIClient
from utils.decorators import hybrid_defer
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
    get_smogon_url,
    truncate_text,
    validate_and_truncate_embed,
)
from utils.validators import (
    sanitize_input,
    validate_generation,
    validate_pokemon_name,
    validate_shiny_generation,
    validate_tier,
)

logger = logging.getLogger("smogon_bot.smogon")


class Smogon(commands.Cog):
    """Cog for fetching Smogon competitive sets and Pokemon data"""

    def __init__(self, bot: commands.Bot):
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
    @commands.cooldown(1, SMOGON_COMMAND_COOLDOWN, commands.BucketType.user)
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
        await self._process_smogon_command(ctx, pokemon, generation, tier)

    @hybrid_defer
    async def _process_smogon_command(
        self,
        ctx: commands.Context,
        pokemon: str,
        generation: str,
        tier: Optional[str],
    ):
        """Process the smogon command logic with validation"""

        # Sanitize and validate pokemon name
        pokemon = sanitize_input(pokemon)
        is_valid, error_msg = validate_pokemon_name(pokemon)
        if not is_valid:
            embed = create_error_embed("Invalid Pokemon Name", error_msg)
            await ctx.send(embed=embed)
            return

        # Validate and normalize generation
        is_valid, error_msg, gen_normalized = validate_generation(generation)
        if not is_valid:
            embed = create_error_embed("Invalid Generation", error_msg)
            await ctx.send(embed=embed)
            return

        # Normalize tier if provided
        tier_normalized = None
        if tier:
            is_valid, error_msg, tier_normalized = validate_tier(tier)
            if not is_valid:
                embed = create_error_embed("Invalid Tier", error_msg)
                await ctx.send(embed=embed)
                return

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
                logger.error(f"Error fetching {tier_normalized}: {e}", exc_info=True)
                embed = create_error_embed(
                    "Error",
                    f"Failed to fetch data for **{tier_normalized.upper()}**. "
                    f"The tier may not exist or the service is temporarily unavailable.",
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
                    "An error occurred while searching for the Pokemon. "
                    "The service may be temporarily unavailable. Please try again later.",
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
            author_id=ctx.author.id,
            timeout=180,
        )

        # Send message and store reference
        message = await ctx.send(embed=embed, view=view)
        view.message = message

    @commands.hybrid_command(
        name="effortvalue",
        description="Get EV yield when defeating a Pokemon",
        aliases=["ev", "evyield", "yield"],
    )
    @commands.cooldown(1, EFFORTVALUE_COMMAND_COOLDOWN, commands.BucketType.user)
    async def effortvalue(self, ctx: commands.Context, pokemon: str):
        """
        Get the effort values (EVs) a Pokemon yields when defeated

        Args:
            pokemon: Pokemon name (e.g., garchomp, landorus-therian)

        Examples:
            .effortvalue garchomp
            .ev blissey
            /effortvalue chansey
        """
        await self._process_ev_command(ctx, pokemon)

    @hybrid_defer
    async def _process_ev_command(self, ctx: commands.Context, pokemon: str):
        """Process the EV yield command logic with validation"""

        # Sanitize and validate pokemon name
        pokemon = sanitize_input(pokemon)
        is_valid, error_msg = validate_pokemon_name(pokemon)
        if not is_valid:
            embed = create_error_embed("Invalid Pokemon Name", error_msg)
            await ctx.send(embed=embed)
            return

        try:
            ev_data = await self.api_client.get_pokemon_ev_yield(pokemon)

            if not ev_data:
                embed = create_error_embed(
                    "Pokemon Not Found",
                    f"Could not find EV yield data for **{capitalize_pokemon_name(pokemon)}**.\n\n"
                    f"**Suggestions:**\n"
                    f"• Check spelling\n"
                    f"• Use hyphens for forms: `landorus-therian`\n"
                    f"• Try the base form without regional variants",
                )
                await ctx.send(embed=embed)
                return

            # Create embed
            embed = self.create_ev_embed(pokemon, ev_data)
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in EV command: {e}", exc_info=True)
            embed = create_error_embed(
                "Error",
                "An error occurred while fetching EV yield data. "
                "The service may be temporarily unavailable. Please try again later.",
            )
            await ctx.send(embed=embed)

    def create_ev_embed(self, pokemon_name: str, ev_data: dict) -> discord.Embed:
        """
        Create Discord embed for EV yield

        Args:
            pokemon_name: Pokemon name
            ev_data: EV yield data from PokeAPI

        Returns:
            Discord embed
        """
        pokemon_display = capitalize_pokemon_name(pokemon_name)
        ev_yields = ev_data["ev_yields"]

        # Build EV yield string
        ev_parts = []
        stat_abbrev = {
            "hp": "HP",
            "attack": "Atk",
            "defense": "Def",
            "special-attack": "SpA",
            "special-defense": "SpD",
            "speed": "Spe",
        }

        for stat_key, stat_short in stat_abbrev.items():
            effort = ev_yields.get(stat_key, 0)
            if effort > 0:
                ev_parts.append(f"+{effort} {stat_short}")

        if ev_parts:
            ev_string = ", ".join(ev_parts)
        else:
            ev_string = "No EVs"

        # Create embed
        embed = discord.Embed(
            title=pokemon_display,
            description=ev_string,
            color=BOT_COLOR,
        )

        # Add sprite if available
        if ev_data.get("sprite"):
            embed.set_thumbnail(url=ev_data["sprite"])

        return embed

    @commands.hybrid_command(
        name="sprite",
        description="Get a Pokemon sprite image",
        aliases=["img", "image", "pic"],
    )
    @commands.cooldown(1, SPRITE_COMMAND_COOLDOWN, commands.BucketType.user)
    async def sprite(
        self,
        ctx: commands.Context,
        pokemon: str,
        shiny: str = "no",
        generation: int = 9,
    ):
        """
        Get a Pokemon sprite image

        Args:
            pokemon: Pokemon name (e.g., garchomp, landorus-therian)
            shiny: Show shiny sprite - "yes" or "no" (default: no)
            generation: Generation 1-9 (default: 9)

        Examples:
            .sprite garchomp
            .sprite charizard yes
            .sprite pikachu no 1
            /sprite mewtwo yes 1
        """
        await self._process_sprite_command(ctx, pokemon, shiny, generation)

    @hybrid_defer
    async def _process_sprite_command(
        self, ctx: commands.Context, pokemon: str, shiny: str, generation: int
    ):
        """Process the sprite command logic with validation"""

        # Sanitize and validate pokemon name
        pokemon = sanitize_input(pokemon)
        is_valid, error_msg = validate_pokemon_name(pokemon)
        if not is_valid:
            embed = create_error_embed("Invalid Pokemon Name", error_msg)
            await ctx.send(embed=embed)
            return

        # Parse shiny parameter
        shiny_bool = shiny.lower() in ["yes", "y", "true", "1", "shiny"]

        # Validate shiny + generation combination
        is_valid, error_msg = validate_shiny_generation(shiny_bool, generation)
        if not is_valid:
            embed = create_error_embed("Invalid Request", error_msg)
            await ctx.send(embed=embed)
            return

        try:
            sprite_data = await self.api_client.get_pokemon_sprite(
                pokemon, shiny_bool, generation
            )

            if not sprite_data:
                embed = create_error_embed(
                    "Sprite Not Found",
                    f"Could not find sprite for **{capitalize_pokemon_name(pokemon)}**.\n\n"
                    f"**Suggestions:**\n"
                    f"• Check spelling\n"
                    f"• Use hyphens for forms: `landorus-therian`\n"
                    f"• Some Pokemon may not have sprites for older generations",
                )
                await ctx.send(embed=embed)
                return

            # Check if Pokemon didn't exist in that generation
            if sprite_data.get("error") == "pokemon_not_in_generation":
                introduced_gen = sprite_data.get("introduced_gen")
                requested_gen = sprite_data.get("requested_gen")

                embed = create_error_embed(
                    "Pokemon Not Available",
                    f"**{capitalize_pokemon_name(pokemon)}** was introduced in **Generation {introduced_gen}**.\n\n"
                    f"It did not exist in Generation {requested_gen}.\n\n"
                    f"Try `/sprite {pokemon} {shiny} {introduced_gen}` or higher.",
                )
                await ctx.send(embed=embed)
                return

            # Create embed
            embed = self.create_sprite_embed(pokemon, sprite_data)
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in sprite command: {e}", exc_info=True)
            embed = create_error_embed(
                "Error",
                "An error occurred while fetching sprite. "
                "The service may be temporarily unavailable. Please try again later.",
            )
            await ctx.send(embed=embed)

    def create_sprite_embed(
        self, pokemon_name: str, sprite_data: dict
    ) -> discord.Embed:
        """
        Create Discord embed for Pokemon sprite

        Args:
            pokemon_name: Pokemon name
            sprite_data: Sprite data from PokeAPI

        Returns:
            Discord embed
        """
        pokemon_display = capitalize_pokemon_name(pokemon_name)

        # Build title with shiny indicator
        if sprite_data.get("shiny", False):
            title = f"​​★ {pokemon_display}"
        else:
            title = pokemon_display

        # Add generation info
        gen_text = f"Generation {sprite_data.get('generation', 9)}"

        # Create embed with sprite as image
        embed = discord.Embed(
            title=title,
            description=gen_text,
            color=BOT_COLOR,
        )

        # Set the sprite as the main image (larger display)
        if sprite_data.get("sprite_url"):
            embed.set_image(url=sprite_data["sprite_url"])

        return embed

    @commands.hybrid_command(
        name="dmgcalc",
        description="Get link to Showdown damage calculator",
        aliases=["calc", "damagecalc", "calculator"],
    )
    async def dmgcalc(self, ctx: commands.Context):
        """
        Get link to Pokemon Showdown damage calculator

        Examples:
            .dmgcalc
            /dmgcalc
        """
        embed = discord.Embed(
            title="Pokemon Showdown Damage Calculator",
            url="https://calc.pokemonshowdown.com/",
            description="Click the title to open the calculator!",
            color=BOT_COLOR,
        )

        await ctx.send(embed=embed)

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

        # Generate Smogon URL
        smogon_url = get_smogon_url(pokemon_name, generation, tier)

        # Truncate set name if needed
        display_set_name = truncate_text(set_name, 200, smart=True)

        embed = discord.Embed(
            title=truncate_text(f"{pokemon_display} - {display_set_name}", 256),
            description=f"**Format:** {format_display}",
            color=BOT_COLOR,
            url=smogon_url,
        )

        # Basic info
        level = set_info.get("level", 100)

        # Ability
        ability_raw = set_info.get("ability")
        if ability_raw:
            ability = format_ability(ability_raw)
            embed.add_field(name="Ability", value=ability, inline=True)
        else:
            embed.add_field(name="Ability", value="—", inline=True)

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
            text=f"Click title for full analysis • Level {level} • {set_count}"
        )

        # Validate and truncate if needed
        embed = validate_and_truncate_embed(embed)

        return embed


class SetSelectorView(discord.ui.View):
    """
    Interactive view with dropdowns for generation, format, and set selection

    Features:
    - Generation selector (Gen 1-9)
    - Format selector (shows only formats where Pokemon exists)
    - Set selector (shows all sets in selected format, warns if >25)
    - Author-only interaction (prevents others from using buttons)
    """

    def __init__(
        self,
        pokemon: str,
        all_formats: Dict[str, dict],
        generation: str,
        current_format: str,
        api_client: SmogonAPIClient,
        cog: Smogon,
        author_id: int,
        timeout: int = 180,
    ):
        super().__init__(timeout=timeout)
        self.pokemon = pokemon
        self.all_formats = all_formats
        self.generation = generation
        self.current_format = current_format
        self.api_client = api_client
        self.cog = cog
        self.author_id = author_id
        self.current_set_index = 0
        self.message: Optional[discord.Message] = None

        # Add dropdowns
        self.add_generation_selector()
        self.add_format_selector()
        self.add_set_selector()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Check if the user interacting is the command author

        Args:
            interaction: Discord interaction

        Returns:
            True if user is authorized, False otherwise
        """
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the command author can use these buttons!", ephemeral=True
            )
            return False
        return True

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
                    label=display_name[:100],
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
                    label=set_name[:100],
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
        """
        Handle generation dropdown selection

        Fetches all formats for the new generation and updates the view.
        Shows error if Pokemon not found in selected generation.
        """
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
        """
        Handle format dropdown selection

        Switches to the selected format and displays the first set.
        """
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
        """
        Handle set dropdown selection

        Displays the selected moveset.
        """
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
            except discord.NotFound:
                logger.debug("Message was deleted before timeout")
            except discord.HTTPException as e:
                logger.error(f"Error removing buttons on timeout: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in on_timeout: {e}")


async def setup(bot: commands.Bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(Smogon(bot))
    logger.info("Smogon cog loaded successfully")
