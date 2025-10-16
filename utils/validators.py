"""
Input validation and sanitization functions
"""

from typing import Optional, Tuple

import discord

from config.settings import GENERATION_MAP, TIER_MAP
from utils.constants import (
    DISCORD_EMBED_FIELD_COUNT_LIMIT,
    DISCORD_EMBED_TOTAL_LIMIT,
    MAX_POKEMON_NAME_LENGTH,
    MIN_POKEMON_NAME_LENGTH,
    POKEMON_NAME_PATTERN,
)


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially harmful characters

    Args:
        text: Raw user input

    Returns:
        Sanitized string
    """
    if not text:
        return ""

    # Remove leading/trailing whitespace
    text = text.strip()

    # Keep only alphanumeric, hyphens, underscores, and spaces
    text = "".join(c for c in text if c.isalnum() or c in "-_ ")

    return text


def validate_pokemon_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Pokemon name

    Args:
        name: Pokemon name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Pokemon name cannot be empty."

    if len(name) < MIN_POKEMON_NAME_LENGTH:
        return (
            False,
            f"Pokemon name must be at least {MIN_POKEMON_NAME_LENGTH} character.",
        )

    if len(name) > MAX_POKEMON_NAME_LENGTH:
        return (
            False,
            f"Pokemon name is too long (max {MAX_POKEMON_NAME_LENGTH} characters).",
        )

    if not POKEMON_NAME_PATTERN.match(name):
        return (
            False,
            "Pokemon name contains invalid characters. Use only letters, numbers, hyphens, and spaces.",
        )

    return True, None


def validate_generation(generation: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and normalize generation input

    Args:
        generation: Generation string (e.g., 'gen9', '9', 'gen1')

    Returns:
        Tuple of (is_valid, error_message, normalized_generation)
    """
    if not generation:
        return True, None, "gen9"  # Default

    gen_input = generation.lower().strip()
    gen_normalized = GENERATION_MAP.get(gen_input, gen_input)

    if (
        not gen_normalized.startswith("gen")
        or gen_normalized not in GENERATION_MAP.values()
    ):
        valid_gens = ", ".join(sorted(set(GENERATION_MAP.values())))
        return False, f"Invalid generation. Valid options: {valid_gens}", None

    return True, None, gen_normalized


def validate_tier(tier: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and normalize tier input

    Args:
        tier: Tier string (e.g., 'ou', 'ubers')

    Returns:
        Tuple of (is_valid, error_message, normalized_tier)
    """
    if not tier:
        return True, None, None  # Tier is optional

    tier_input = tier.lower().strip()
    tier_normalized = TIER_MAP.get(tier_input, tier_input)

    # We don't strictly validate tier here since formats can vary by generation
    # Just normalize it
    return True, None, tier_normalized


def validate_embed_size(embed: discord.Embed) -> Tuple[bool, Optional[str]]:
    """
    Validate Discord embed size limits

    Args:
        embed: Discord embed to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Calculate total characters
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

    # Check field count
    if len(embed.fields) > DISCORD_EMBED_FIELD_COUNT_LIMIT:
        return (
            False,
            f"Too many fields ({len(embed.fields)} > {DISCORD_EMBED_FIELD_COUNT_LIMIT})",
        )

    # Check total size
    if total_chars > DISCORD_EMBED_TOTAL_LIMIT:
        return (
            False,
            f"Embed too large ({total_chars} > {DISCORD_EMBED_TOTAL_LIMIT} characters)",
        )

    return True, None


def validate_shiny_generation(
    shiny: bool, generation: int
) -> Tuple[bool, Optional[str]]:
    """
    Validate shiny sprite request for generation

    Args:
        shiny: Whether shiny is requested
        generation: Generation number

    Returns:
        Tuple of (is_valid, error_message)
    """
    if shiny and generation == 1:
        return (
            False,
            "Shiny Pokemon were introduced in Generation 2. Try generation 2 or higher.",
        )

    if generation < 1 or generation > 9:
        return False, f"Generation must be between 1 and 9. You provided: {generation}"

    return True, None
