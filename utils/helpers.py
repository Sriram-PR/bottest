from typing import Any, Dict, List, Optional

import discord

from config.settings import FORMAT_NAMES, TYPE_EMOJIS


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


def format_ability(ability: Any) -> str:
    """
    Format ability, handling slash options

    Args:
        ability: Ability (string or list)

    Returns:
        Formatted ability string
    """
    if isinstance(ability, list):
        return " / ".join(ability)
    return str(ability) if ability else "Unknown"


def format_item(item: Any) -> str:
    """
    Format item, handling slash options

    Args:
        item: Item (string or list)

    Returns:
        Formatted item string
    """
    if isinstance(item, list):
        return " / ".join(item)
    return str(item) if item else "None"


def format_nature(nature: Any) -> str:
    """
    Format nature, handling slash options

    Args:
        nature: Nature (string or list)

    Returns:
        Formatted nature string
    """
    if isinstance(nature, list):
        return " / ".join(nature)
    return str(nature) if nature else "Any"


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


def truncate_text(text: str, max_length: int = 1024) -> str:
    """
    Truncate text to fit Discord embed field limits

    Args:
        text: Text to truncate
        max_length: Maximum length (default 1024 for embed fields)

    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


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
    embed = discord.Embed(title=f"❌ {title}", description=description, color=color)
    return embed
