from typing import Any, Dict, List, Optional

import discord

from config.settings import FORMAT_NAMES, SMOGON_DEX_GENS, TYPE_EMOJIS
from utils.constants import (
    DISCORD_EMBED_DESCRIPTION_LIMIT,
    DISCORD_EMBED_TITLE_LIMIT,
    DISCORD_EMBED_TOTAL_LIMIT,
)


def capitalize_pokemon_name(name: str) -> str:
    """
    Properly capitalize Pokemon names with special handling

    Args:
        name: Pokemon name (e.g., 'garchomp', 'landorus-therian')

    Returns:
        Properly formatted name
    """
    # Special cases
    special_cases = {
        "nidoran-f": "Nidoran♀",
        "nidoran-m": "Nidoran♂",
        "mr-mime": "Mr. Mime",
        "mime-jr": "Mime Jr.",
        "type-null": "Type: Null",
        "ho-oh": "Ho-Oh",
        "porygon-z": "Porygon-Z",
        "jangmo-o": "Jangmo-o",
        "hakamo-o": "Hakamo-o",
        "kommo-o": "Kommo-o",
    }

    name_lower = name.lower()
    if name_lower in special_cases:
        return special_cases[name_lower]

    # Handle forms (e.g., "landorus-therian" -> "Landorus-Therian")
    parts = name.split("-")
    capitalized = [part.capitalize() for part in parts]

    return "-".join(capitalized)


def format_generation_tier(generation: str, tier: str) -> str:
    """
    Format generation and tier for display

    Args:
        generation: Generation string (e.g., 'gen9')
        tier: Tier string (e.g., 'ou')

    Returns:
        Formatted string (e.g., 'Gen 9 OU')
    """
    # Extract generation number
    gen_num = generation.replace("gen", "")
    tier_upper = tier.upper()

    # Get full tier name if available
    tier_full_name = FORMAT_NAMES.get(tier.lower())

    if tier_full_name:
        tier_display = f"{tier_upper} ({tier_full_name})"
    else:
        tier_display = tier_upper

    return f"Gen {gen_num} {tier_display}"


def get_format_display_name(tier: str, set_count: Optional[int] = None) -> str:
    """
    Get display name for a format/tier

    Args:
        tier: Tier string (e.g., 'ou', 'doublesou')
        set_count: Optional number of sets to display

    Returns:
        Formatted display name (e.g., 'OU - 5 sets')
    """
    tier_upper = tier.upper()
    display = tier_upper

    if set_count is not None:
        display += f" - {set_count} set{'s' if set_count != 1 else ''}"

    return display


def format_move_list(moves: List[Any]) -> str:
    """
    Format moves for display, handling slash options

    Args:
        moves: List of moves (can be strings or lists for slash options)

    Returns:
        Formatted move string
    """
    if not moves:
        return "No moves specified"

    formatted = []
    for move in moves:
        if isinstance(move, list):
            formatted.append(" / ".join(move))
        else:
            formatted.append(str(move))

    return "\n".join(f"• {move}" for move in formatted)


def format_evs(evs: Dict[str, int]) -> str:
    """
    Format EVs for display

    Args:
        evs: Dictionary of EVs (e.g., {'hp': 252, 'atk': 252})

    Returns:
        Formatted EV string
    """
    if not evs:
        return "No EVs specified"

    ev_order = ["hp", "atk", "def", "spa", "spd", "spe"]
    formatted = []

    for stat in ev_order:
        if stat in evs and evs[stat] > 0:
            formatted.append(f"{evs[stat]} {stat.upper()}")

    return " / ".join(formatted) if formatted else "No EVs specified"


def format_ivs(ivs: Dict[str, int]) -> Optional[str]:
    """
    Format IVs for display (only shows non-31 IVs)

    Args:
        ivs: Dictionary of IVs

    Returns:
        Formatted IV string or None if all 31
    """
    if not ivs:
        return None

    iv_order = ["hp", "atk", "def", "spa", "spd", "spe"]
    formatted = []

    for stat in iv_order:
        if stat in ivs and ivs[stat] != 31:
            formatted.append(f"{ivs[stat]} {stat.upper()}")

    return " / ".join(formatted) if formatted else None


def _format_field_generic(
    field: Any, default: str = "—", none_value: str = "None"
) -> str:
    """
    Generic formatter for ability/item/nature fields with slash options

    Args:
        field: Field value (string or list)
        default: Default value for empty lists
        none_value: Value to return if field is None/empty

    Returns:
        Formatted field string
    """
    if isinstance(field, list):
        filtered = [str(f).strip() for f in field if f]
        return " / ".join(filtered) if filtered else default

    if field:
        return str(field).strip()

    return none_value


def format_ability(ability: Any) -> str:
    """
    Format ability, handling slash options

    Args:
        ability: Ability (string or list)

    Returns:
        Formatted ability string
    """
    return _format_field_generic(ability, default="—", none_value="—")


def format_item(item: Any) -> str:
    """
    Format item, handling slash options

    Args:
        item: Item (string or list)

    Returns:
        Formatted item string
    """
    return _format_field_generic(item, default="None", none_value="None")


def format_nature(nature: Any) -> str:
    """
    Format nature, handling slash options

    Args:
        nature: Nature (string or list)

    Returns:
        Formatted nature string
    """
    return _format_field_generic(nature, default="Any", none_value="Any")


def format_tera_type(tera: Any) -> Optional[str]:
    """
    Format Tera type with emoji

    Args:
        tera: Tera type (string or list)

    Returns:
        Formatted Tera type string or None
    """
    if not tera:
        return None

    if isinstance(tera, list):
        formatted = []
        for t in tera:
            emoji = TYPE_EMOJIS.get(t.lower(), "•")
            formatted.append(f"{emoji} {t}")
        return " / ".join(formatted)
    else:
        emoji = TYPE_EMOJIS.get(tera.lower(), "•")
        return f"{emoji} {tera}"


def truncate_text(text: str, max_length: int = 1024, smart: bool = True) -> str:
    """
    Truncate text to fit Discord embed field limits

    Args:
        text: Text to truncate
        max_length: Maximum length (default 1024 for embed fields)
        smart: If True, try to truncate at word boundaries

    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text

    if smart:
        # Try to truncate at last space before max_length
        truncate_point = text.rfind(" ", 0, max_length - 3)
        if truncate_point > max_length // 2:  # Only if we find a space in latter half
            return text[:truncate_point] + "..."

    # Fallback to hard truncate
    return text[: max_length - 3] + "..."


def get_smogon_url(pokemon: str, generation: str, tier: str) -> str:
    """
    Generate Smogon Dex URL for a Pokemon set

    Args:
        pokemon: Pokemon name (e.g., 'garchomp', 'landorus-therian')
        generation: Generation string (e.g., 'gen9')
        tier: Tier string (e.g., 'ou', '1v1')

    Returns:
        Smogon Dex URL
    """
    # Get Smogon generation code
    gen_code = SMOGON_DEX_GENS.get(generation.lower(), "sv")  # Default to SV

    # Format pokemon name (lowercase, keep hyphens)
    pokemon_formatted = pokemon.lower().strip().replace(" ", "-")

    # Format tier (lowercase)
    tier_formatted = tier.lower().strip()

    # Build URL
    url = f"https://www.smogon.com/dex/{gen_code}/pokemon/{pokemon_formatted}/{tier_formatted}/"

    return url


def create_error_embed(
    title: str, description: str, color: int = 0xFF0000
) -> discord.Embed:
    """
    Create a standardized error embed

    Args:
        title: Error title
        description: Error description
        color: Embed color (default red)

    Returns:
        Discord embed
    """
    embed = discord.Embed(
        title=f"❌ {title}",
        description=truncate_text(description, DISCORD_EMBED_DESCRIPTION_LIMIT),
        color=color,
    )
    return embed


def validate_and_truncate_embed(embed: discord.Embed) -> discord.Embed:
    """
    Validate and truncate embed to fit within Discord limits

    Args:
        embed: Discord embed to validate

    Returns:
        Modified embed that fits within limits
    """
    # Truncate title if needed
    if embed.title and len(embed.title) > DISCORD_EMBED_TITLE_LIMIT:
        embed.title = embed.title[: DISCORD_EMBED_TITLE_LIMIT - 3] + "..."

    # Truncate description if needed
    if embed.description and len(embed.description) > DISCORD_EMBED_DESCRIPTION_LIMIT:
        embed.description = truncate_text(
            embed.description, DISCORD_EMBED_DESCRIPTION_LIMIT
        )

    # Check total character count
    total_chars = 0
    if embed.title:
        total_chars += len(embed.title)
    if embed.description:
        total_chars += len(embed.description)
    if embed.footer.text:
        total_chars += len(embed.footer.text)
    if embed.author.name:
        total_chars += len(embed.author.name)

    for field in embed.fields:
        total_chars += len(field.name) + len(field.value)

    # If over limit, we need to remove some fields
    if total_chars > DISCORD_EMBED_TOTAL_LIMIT:
        # Calculate how much we need to remove
        excess = total_chars - DISCORD_EMBED_TOTAL_LIMIT

        # Try to truncate the description first
        if embed.description and len(embed.description) > excess:
            new_desc_length = max(100, len(embed.description) - excess - 50)
            embed.description = truncate_text(embed.description, new_desc_length)

    return embed
