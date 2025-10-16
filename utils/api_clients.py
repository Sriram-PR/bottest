import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

import aiohttp

from config.settings import (
    API_REQUEST_TIMEOUT,
    CACHE_CLEANUP_INTERVAL,
    CACHE_TIMEOUT,
    FORMATS_BY_GEN,
    MAX_CACHE_SIZE,
    MAX_CONCURRENT_API_REQUESTS,
    POKEAPI_URL,
    PRIORITY_FORMATS,
    SMOGON_SETS_URL,
)
from utils.decorators import retry_on_error

logger = logging.getLogger("smogon_bot.api")


class SmogonAPIClient:
    """
    Client for fetching competitive sets from Smogon and Pokemon data from PokeAPI

    Features:
    - LRU cache with size limit and auto-cleanup
    - Rate limiting with semaphore
    - Automatic retry on failures
    - Parallel format fetching
    - Cache statistics tracking
    """

    def __init__(self):
        self.base_url = SMOGON_SETS_URL
        self.session: Optional[aiohttp.ClientSession] = None

        # LRU cache using OrderedDict
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()

        # Rate limiting
        self._rate_limiter = asyncio.Semaphore(MAX_CONCURRENT_API_REQUESTS)

        # Cache statistics
        self.cache_hits = 0
        self.cache_misses = 0

        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_closing = False

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with timeout configuration"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=API_REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "Pokemon-Smogon-Discord-Bot/2.0"},
            )

            # Start cache cleanup task
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cache_cleanup_loop())
                logger.info("Started cache cleanup background task")

        return self.session

    async def close(self):
        """Close the aiohttp session and cleanup tasks"""
        self._is_closing = True

        # Cancel cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Cancelled cache cleanup task")

        # Close session
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(
                f"API client session closed (Cache stats - Hits: {self.cache_hits}, Misses: {self.cache_misses})"
            )

    async def _cache_cleanup_loop(self):
        """Background task to periodically clean expired cache entries"""
        while not self._is_closing:
            try:
                await asyncio.sleep(CACHE_CLEANUP_INTERVAL)
                self._cleanup_expired_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache cleanup task: {e}")

    def _cleanup_expired_cache(self):
        """Remove expired entries from cache"""
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, timestamp) in self.cache.items()
            if current_time - timestamp > CACHE_TIMEOUT
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")

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
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                self.cache_hits += 1
                logger.debug(f"Cache hit for {key}")
                return data
            else:
                # Remove expired cache
                del self.cache[key]
                logger.debug(f"Cache expired for {key}")

        self.cache_misses += 1
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

    @retry_on_error(max_retries=3)
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
            f"Searching for {pokemon} in {generation} across {len(available_formats)} formats"
        )

        # Search ALL formats in parallel
        async with self._rate_limiter:
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
                logger.info(f"✓ Found {pokemon} in {generation}{tier}")

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

    @retry_on_error(max_retries=3)
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

            logger.debug(f"Fetching {url}")

            async with self._rate_limiter:
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

                        logger.debug(f"Pokemon {pokemon} not found in {format_id}")
                        return None

                    elif resp.status == 404:
                        logger.debug(f"Format {format_id} not found (404)")
                        return None
                    else:
                        logger.warning(f"API error {resp.status} for {url}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {format_id} for {pokemon}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {format_id}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Error fetching Smogon sets for {pokemon}: {e}", exc_info=True
            )
            return None

    @retry_on_error(max_retries=3)
    async def get_pokemon_ev_yield(self, pokemon: str) -> Optional[Dict]:
        """
        Fetch EV yield data from PokeAPI

        Args:
            pokemon: Pokemon name (e.g., 'garchomp', 'landorus-therian')

        Returns:
            Dictionary with EV yields or None if not found
        """
        pokemon = pokemon.lower().strip().replace(" ", "-")

        cache_key = f"ev_yield:{pokemon}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            session = await self.get_session()
            url = f"{POKEAPI_URL}/pokemon/{pokemon}"

            logger.debug(f"Fetching EV yield from PokeAPI: {url}")

            async with self._rate_limiter:
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

                        result = {
                            "ev_yields": ev_yields,
                            "total": total_evs,
                            "name": data.get("name"),
                            "id": data.get("id"),
                            "sprite": data.get("sprites", {}).get("front_default"),
                            "types": [t["type"]["name"] for t in data.get("types", [])],
                        }

                        self._set_cache(cache_key, result)
                        logger.info(f"Found EV yield for {pokemon}")
                        return result

                    elif resp.status == 404:
                        logger.debug(f"Pokemon {pokemon} not found in PokeAPI")
                        return None
                    else:
                        logger.warning(f"PokeAPI error {resp.status} for {pokemon}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching EV yield for {pokemon}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching EV yield: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching EV yield for {pokemon}: {e}", exc_info=True)
            return None

    @retry_on_error(max_retries=3)
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
        pokemon = pokemon.lower().strip().replace(" ", "-")

        cache_key = f"sprite:{pokemon}:{shiny}:{generation}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            session = await self.get_session()

            # First, get Pokemon species data to check generation
            species_url = f"{POKEAPI_URL}/pokemon-species/{pokemon}"

            async with self._rate_limiter:
                async with session.get(species_url) as species_resp:
                    if species_resp.status == 200:
                        species_data = await species_resp.json()

                        # Get generation introduced
                        gen_data = species_data.get("generation", {})
                        gen_url = gen_data.get("url", "")

                        try:
                            introduced_gen = int(gen_url.rstrip("/").split("/")[-1])
                        except (ValueError, IndexError):
                            introduced_gen = 1

                        # Check if Pokemon existed in requested generation
                        if generation < introduced_gen:
                            logger.debug(
                                f"{pokemon} was introduced in Gen {introduced_gen}, "
                                f"cannot show Gen {generation} sprite"
                            )
                            return {
                                "error": "pokemon_not_in_generation",
                                "introduced_gen": introduced_gen,
                                "requested_gen": generation,
                            }
                    elif species_resp.status == 404:
                        logger.debug(f"Pokemon species {pokemon} not found in PokeAPI")
                        return None

            # Now fetch the sprite
            url = f"{POKEAPI_URL}/pokemon/{pokemon}"

            logger.debug(f"Fetching sprite from PokeAPI: {url}")

            async with self._rate_limiter:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sprites = data.get("sprites", {})

                        sprite_url = None

                        gen_map = {
                            1: "generation-i",
                            2: "generation-ii",
                            3: "generation-iii",
                            4: "generation-iv",
                            5: "generation-v",
                            6: "generation-vi",
                            7: "generation-vii",
                            8: "generation-viii",
                            9: None,
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

                                game_keys = list(gen_sprites.keys())
                                if game_keys:
                                    for game_key in game_keys:
                                        game_sprite = gen_sprites[game_key]
                                        if shiny:
                                            sprite_url = game_sprite.get("front_shiny")
                                        else:
                                            sprite_url = game_sprite.get(
                                                "front_default"
                                            )
                                        if sprite_url:
                                            break

                        if not sprite_url:
                            logger.debug(
                                f"No sprite found for {pokemon} "
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

                        self._set_cache(cache_key, result)
                        logger.info(f"Found sprite for {pokemon}")
                        return result

                    elif resp.status == 404:
                        logger.debug(f"Pokemon {pokemon} not found in PokeAPI")
                        return None
                    else:
                        logger.warning(f"PokeAPI error {resp.status} for {pokemon}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching sprite for {pokemon}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching sprite: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching sprite for {pokemon}: {e}", exc_info=True)
            return None

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        logger.info("Cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": MAX_CACHE_SIZE,
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "hit_rate": f"{hit_rate:.1f}%",
        }
