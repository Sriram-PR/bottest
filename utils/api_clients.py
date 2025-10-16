import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

import aiohttp

from config.settings import (
    CACHE_TIMEOUT,
    FORMATS_BY_GEN,
    MAX_CACHE_SIZE,
    POKEAPI_URL,
    PRIORITY_FORMATS,
    SMOGON_SETS_URL,
)

logger = logging.getLogger("smogon_bot.api")


class SmogonAPIClient:
    """
    Client for fetching competitive sets from Smogon

    Features:
    - LRU cache with size limit
    - Tier location caching
    - Parallel format fetching
    """

    def __init__(self):
        self.base_url = SMOGON_SETS_URL
        self.session: Optional[aiohttp.ClientSession] = None
        # LRU cache using OrderedDict
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "Pokemon-Smogon-Discord-Bot/1.0"},
            )
        return self.session

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("API client session closed")

    def _get_cached(self, key: str) -> Optional[Any]:
        """
        Get data from cache if not expired (LRU)

        Args:
            key: Cache key

        Returns:
            Cached data or None if expired/not found
        """
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < CACHE_TIMEOUT:
                logger.debug(f"Cache hit for {key}")
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return data
            else:
                # Remove expired cache
                del self.cache[key]
                logger.debug(f"Cache expired for {key}")
        return None

    def _set_cache(self, key: str, data: Any):
        """
        Store data in cache with timestamp (LRU with size limit)

        Args:
            key: Cache key
            data: Data to cache
        """
        # Remove oldest entries if at capacity
        while len(self.cache) >= MAX_CACHE_SIZE:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            logger.debug(f"Evicted cache entry: {oldest_key}")

        self.cache[key] = (data, time.time())
        logger.debug(f"Cached data for {key}")

    async def find_pokemon_in_generation(
        self, pokemon: str, generation: str
    ) -> Dict[str, Dict]:
        """
        Find a Pokemon across all formats in a generation using parallel requests

        Args:
            pokemon: Pokemon name
            generation: Generation (e.g., 'gen9')

        Returns:
            Dictionary mapping format_id to sets data
            Example: {'ou': {...sets...}, 'ubers': {...sets...}}
        """
        # Check if we have cached tier locations for this pokemon
        tier_cache_key = f"tier_location:{generation}:{pokemon}"
        cached_tiers = self._get_cached(tier_cache_key)

        if cached_tiers:
            logger.info(f"Using cached tier locations for {pokemon} in {generation}")
            # Fetch only the known tiers
            result = {}
            for tier in cached_tiers:
                sets = await self.get_sets(pokemon, generation, tier)
                if sets:
                    result[tier] = sets
            return result

        # Get available formats for this generation
        available_formats = FORMATS_BY_GEN.get(generation, PRIORITY_FORMATS)

        logger.info(
            f"Searching all formats for {pokemon} in {generation}: {available_formats}"
        )

        # Search ALL formats in parallel (don't stop at priority)
        tasks = []
        for tier in available_formats:
            tasks.append(self._fetch_format(pokemon, generation, tier))

        # Execute all parallel requests
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect ALL successful results
        found_formats = {}
        for tier, result in zip(available_formats, results):
            if result and not isinstance(result, Exception):
                found_formats[tier] = result
                logger.info(f"Found {pokemon} in {generation}{tier}")

        # Cache tier locations if found
        if found_formats:
            self._set_cache(tier_cache_key, list(found_formats.keys()))

        return found_formats

    async def _fetch_format(
        self, pokemon: str, generation: str, tier: str
    ) -> Optional[Dict]:
        """
        Internal method to fetch a specific format and find pokemon

        Args:
            pokemon: Pokemon name
            generation: Generation
            tier: Tier/format

        Returns:
            Sets data for the pokemon or None
        """
        try:
            sets = await self.get_sets(pokemon, generation, tier)
            return sets
        except Exception as e:
            logger.debug(f"Error fetching {generation}{tier}: {e}")
            return None

    async def get_sets(
        self, pokemon: str, generation: str = "gen9", tier: str = "ou"
    ) -> Optional[Dict]:
        """
        Fetch competitive sets from Smogon for a specific format

        Args:
            pokemon: Pokemon name (e.g., 'garchomp', 'landorus-therian')
            generation: Generation (e.g., 'gen9', 'gen8')
            tier: Competitive tier (e.g., 'ou', 'uu', 'ubers')

        Returns:
            Dictionary of sets or None if not found
        """
        # Normalize inputs
        pokemon = pokemon.lower().strip().replace(" ", "-")
        generation = generation.lower().strip()
        tier = tier.lower().strip()

        # Construct format ID
        format_id = f"{generation}{tier}"

        # Check cache
        cache_key = f"{format_id}:{pokemon}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            session = await self.get_session()
            url = f"{self.base_url}/{format_id}.json"

            logger.info(f"Fetching {url}")

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # Search for Pokemon in the data
                    # Try exact match first
                    for poke_name, sets in data.items():
                        if poke_name.lower().replace(" ", "-") == pokemon:
                            self._set_cache(cache_key, sets)
                            logger.info(f"Found sets for {pokemon} in {format_id}")
                            return sets

                    # Try partial match (for forms like "Landorus-Therian")
                    for poke_name, sets in data.items():
                        if pokemon in poke_name.lower().replace(" ", "-"):
                            self._set_cache(cache_key, sets)
                            logger.info(
                                f"Found sets for {pokemon} (matched {poke_name}) in {format_id}"
                            )
                            return sets

                    logger.warning(f"Pokemon {pokemon} not found in {format_id}")
                    return None

                elif resp.status == 404:
                    logger.warning(f"Format {format_id} not found (404)")
                    return None
                else:
                    logger.error(f"API error {resp.status} for {url}")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {format_id}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Error fetching Smogon sets for {pokemon}: {e}", exc_info=True
            )
            return None

    async def get_format_list(self, generation: str = "gen9") -> Optional[Dict]:
        """
        Get all Pokemon available in a specific generation's data

        Args:
            generation: Generation (e.g., 'gen9')

        Returns:
            Dictionary of all sets or None
        """
        cache_key = f"format_list:{generation}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            session = await self.get_session()
            url = f"{self.base_url}/{generation}.json"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._set_cache(cache_key, data)
                    return data
                else:
                    logger.error(f"Failed to fetch format list: {resp.status}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching format list: {e}", exc_info=True)
            return None

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        logger.info("Cache cleared")

    async def get_pokemon_ev_yield(self, pokemon: str) -> Optional[Dict]:
        """
        Fetch EV yield data from PokeAPI

        Args:
            pokemon: Pokemon name (e.g., 'garchomp', 'landorus-therian')

        Returns:
            Dictionary with EV yields or None if not found
            Example: {'hp': 0, 'attack': 3, 'defense': 0, 'special-attack': 0, 'special-defense': 0, 'speed': 0}
        """
        # Normalize pokemon name
        pokemon = pokemon.lower().strip().replace(" ", "-")

        # Check cache
        cache_key = f"ev_yield:{pokemon}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            session = await self.get_session()
            url = f"{POKEAPI_URL}/pokemon/{pokemon}"

            logger.info(f"Fetching EV yield from PokeAPI: {url}")

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # Extract EV yields from stats
                    ev_yields = {}
                    total_evs = 0

                    for stat in data.get("stats", []):
                        stat_name = stat["stat"]["name"]
                        effort = stat["effort"]
                        ev_yields[stat_name] = effort
                        total_evs += effort

                    # Add total and Pokemon info
                    result = {
                        "ev_yields": ev_yields,
                        "total": total_evs,
                        "name": data.get("name"),
                        "id": data.get("id"),
                        "sprite": data.get("sprites", {}).get("front_default"),
                        "types": [t["type"]["name"] for t in data.get("types", [])],
                    }

                    # Cache for longer (EV yields never change)
                    self._set_cache(cache_key, result)
                    logger.info(f"Found EV yield for {pokemon}: {ev_yields}")

                    return result

                elif resp.status == 404:
                    logger.warning(f"Pokemon {pokemon} not found in PokeAPI")
                    return None
                else:
                    logger.error(f"PokeAPI error {resp.status} for {pokemon}")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching EV yield: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching EV yield for {pokemon}: {e}", exc_info=True)
            return None

    async def get_pokemon_sprite(
        self, pokemon: str, shiny: bool = False, generation: int = 9
    ) -> Optional[Dict]:
        """
        Fetch Pokemon sprite from PokeAPI

        Args:
            pokemon: Pokemon name (e.g., 'garchomp', 'landorus-therian')
            shiny: Whether to get shiny sprite (default: False)
            generation: Generation number 1-9 (default: 9)

        Returns:
            Dictionary with sprite data or None if not found
        """
        # Normalize pokemon name
        pokemon = pokemon.lower().strip().replace(" ", "-")

        # Check cache
        cache_key = f"sprite:{pokemon}:{shiny}:{generation}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            session = await self.get_session()

            # First, get Pokemon species data to check which generation it was introduced
            species_url = f"{POKEAPI_URL}/pokemon-species/{pokemon}"

            async with session.get(species_url) as species_resp:
                if species_resp.status == 200:
                    species_data = await species_resp.json()

                    # Get generation introduced
                    gen_data = species_data.get("generation", {})
                    gen_url = gen_data.get("url", "")

                    # Extract generation number from URL (e.g., ".../generation/4/" -> 4)
                    try:
                        introduced_gen = int(gen_url.rstrip("/").split("/")[-1])
                    except (ValueError, IndexError):
                        introduced_gen = 1  # Fallback to Gen 1 if can't parse

                    # Check if Pokemon existed in requested generation
                    if generation < introduced_gen:
                        logger.warning(
                            f"{pokemon} was introduced in Gen {introduced_gen}, "
                            f"cannot show Gen {generation} sprite"
                        )
                        return {
                            "error": "pokemon_not_in_generation",
                            "introduced_gen": introduced_gen,
                            "requested_gen": generation,
                        }
                elif species_resp.status == 404:
                    logger.warning(f"Pokemon species {pokemon} not found in PokeAPI")
                    return None

            # Now fetch the sprite
            url = f"{POKEAPI_URL}/pokemon/{pokemon}"

            logger.info(f"Fetching sprite from PokeAPI: {url}")

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sprites = data.get("sprites", {})

                    # Get sprite based on generation and shiny
                    sprite_url = None

                    # Try generation-specific sprites first
                    gen_map = {
                        1: "generation-i",
                        2: "generation-ii",
                        3: "generation-iii",
                        4: "generation-iv",
                        5: "generation-v",
                        6: "generation-vi",
                        7: "generation-vii",
                        8: "generation-viii",
                        9: None,  # Gen 9 uses default sprites
                    }

                    if generation == 9:
                        # Use default sprites for Gen 9
                        if shiny:
                            sprite_url = sprites.get("front_shiny")
                        else:
                            sprite_url = sprites.get("front_default")
                    else:
                        gen_key = gen_map.get(generation)
                        if gen_key:
                            versions = sprites.get("versions", {})
                            gen_sprites = versions.get(gen_key, {})

                            # Different generations have different game keys
                            game_keys = list(gen_sprites.keys())
                            if game_keys:
                                # Try first game variant
                                game_sprite = gen_sprites[game_keys[0]]
                                if shiny:
                                    sprite_url = game_sprite.get("front_shiny")
                                else:
                                    sprite_url = game_sprite.get("front_default")

                                # If not found, try other game variants
                                if not sprite_url and len(game_keys) > 1:
                                    for game_key in game_keys[1:]:
                                        game_sprite = gen_sprites[game_key]
                                        if shiny:
                                            sprite_url = game_sprite.get("front_shiny")
                                        else:
                                            sprite_url = game_sprite.get(
                                                "front_default"
                                            )
                                        if sprite_url:
                                            break

                    # Don't fallback to default - if gen-specific sprite not found, return None
                    if not sprite_url:
                        logger.warning(
                            f"No generation-specific sprite found for {pokemon} "
                            f"(shiny={shiny}, gen={generation})"
                        )
                        return None

                    result = {
                        "sprite_url": sprite_url,
                        "name": data.get("name"),
                        "id": data.get("id"),
                        "shiny": shiny,
                        "generation": generation,
                    }

                    # Cache sprite data
                    self._set_cache(cache_key, result)
                    logger.info(f"Found sprite for {pokemon}")

                    return result

                elif resp.status == 404:
                    logger.warning(f"Pokemon {pokemon} not found in PokeAPI")
                    return None
                else:
                    logger.error(f"PokeAPI error {resp.status} for {pokemon}")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching sprite: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching sprite for {pokemon}: {e}", exc_info=True)
            return None
