import asyncio
import logging
import pickle
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import aiohttp

from config.settings import (
    API_REQUEST_TIMEOUT,
    CACHE_CLEANUP_INTERVAL,
    CACHE_PERSIST_TO_DISK,
    CACHE_TIMEOUT,
    COMPREHENSIVE_FORMAT_LIST,
    DATA_DIR,
    FORMAT_CACHE_TIMEOUT,
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
    - Dynamic format discovery (no hardcoded format lists!)
    - LRU cache with size limit and auto-cleanup
    - Disk-based cache persistence across restarts
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

        # Format discovery cache: {generation: {formats_set, timestamp}}
        self.discovered_formats: Dict[str, Tuple[Set[str], float]] = {}

        # Rate limiting
        self._rate_limiter = asyncio.Semaphore(MAX_CONCURRENT_API_REQUESTS)

        # Cache statistics
        self.cache_hits = 0
        self.cache_misses = 0
        self.format_discoveries = 0

        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_closing = False

        # Load cache from disk on initialization
        if CACHE_PERSIST_TO_DISK:
            self._load_cache_from_disk()

    def _get_cache_file(self) -> Path:
        """Get cache file path"""
        return DATA_DIR / "api_cache.pkl"

    def _load_cache_from_disk(self):
        """Load cache from disk if available"""
        cache_file = self._get_cache_file()
        if not cache_file.exists():
            logger.info("No existing cache file found - starting with empty cache")
            return

        try:
            with open(cache_file, "rb") as f:
                loaded_data = pickle.load(f)

            # Load regular cache
            loaded_cache = loaded_data.get("cache", {})
            current_time = time.time()
            valid_entries = 0
            expired_entries = 0

            for key, (data, timestamp) in loaded_cache.items():
                if current_time - timestamp < CACHE_TIMEOUT:
                    self.cache[key] = (data, timestamp)
                    valid_entries += 1
                else:
                    expired_entries += 1

            # Load discovered formats
            loaded_formats = loaded_data.get("discovered_formats", {})
            for gen, (formats_set, timestamp) in loaded_formats.items():
                if current_time - timestamp < FORMAT_CACHE_TIMEOUT:
                    self.discovered_formats[gen] = (formats_set, timestamp)

            logger.info(
                f"✅ Loaded {valid_entries} cache entries and "
                f"{len(self.discovered_formats)} format discoveries from disk "
                f"({expired_entries} expired entries discarded)"
            )
        except Exception as e:
            logger.error(f"❌ Error loading cache from disk: {e}")
            logger.info("Starting with empty cache")

    def _save_cache_to_disk(self):
        """Save cache to disk"""
        if not CACHE_PERSIST_TO_DISK:
            return

        cache_file = self._get_cache_file()

        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Save both regular cache and discovered formats
            save_data = {
                "cache": dict(self.cache),
                "discovered_formats": dict(self.discovered_formats),
            }

            with open(cache_file, "wb") as f:
                pickle.dump(save_data, f, protocol=pickle.HIGHEST_PROTOCOL)

            logger.info(
                f"💾 Saved {len(self.cache)} cache entries and "
                f"{len(self.discovered_formats)} format discoveries to disk"
            )
        except Exception as e:
            logger.error(f"❌ Error saving cache to disk: {e}")

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with timeout configuration"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=API_REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "Pokemon-Smogon-Discord-Bot/2.0"},
            )

            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cache_cleanup_loop())
                logger.info("Started cache cleanup background task")

        return self.session

    async def close(self):
        """Close the aiohttp session and cleanup tasks"""
        self._is_closing = True

        if CACHE_PERSIST_TO_DISK:
            self._save_cache_to_disk()

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Cancelled cache cleanup task")

        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(
                f"API client session closed (Cache: {self.cache_hits} hits / "
                f"{self.cache_misses} misses, Formats discovered: {self.format_discoveries})"
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

        # Clean regular cache
        expired_keys = [
            key
            for key, (_, timestamp) in self.cache.items()
            if current_time - timestamp > CACHE_TIMEOUT
        ]
        for key in expired_keys:
            del self.cache[key]

        # Clean format discovery cache
        expired_gens = [
            gen
            for gen, (_, timestamp) in self.discovered_formats.items()
            if current_time - timestamp > FORMAT_CACHE_TIMEOUT
        ]
        for gen in expired_gens:
            del self.discovered_formats[gen]

        if expired_keys or expired_gens:
            logger.debug(
                f"Cleaned {len(expired_keys)} cache entries and "
                f"{len(expired_gens)} format discoveries"
            )

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get data from cache if not expired (LRU)"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < CACHE_TIMEOUT:
                self.cache.move_to_end(key)
                self.cache_hits += 1
                logger.debug(f"Cache hit for {key}")
                return data
            else:
                del self.cache[key]
                logger.debug(f"Cache expired for {key}")

        self.cache_misses += 1
        return None

    def _set_cache(self, key: str, data: Any):
        """Store data in cache with timestamp (LRU with size limit)"""
        while len(self.cache) >= MAX_CACHE_SIZE:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            logger.debug(f"Evicted cache entry: {oldest_key}")

        self.cache[key] = (data, time.time())
        logger.debug(f"Cached data for {key}")

    async def discover_formats_for_generation(self, generation: str) -> Set[str]:
        """
        Dynamically discover which formats exist for a generation

        This tries all possible formats and caches which ones actually exist.
        No more hardcoded format lists!

        Args:
            generation: Generation string (e.g., 'gen9')

        Returns:
            Set of format IDs that exist for this generation
        """
        # Check cache first
        if generation in self.discovered_formats:
            formats_set, timestamp = self.discovered_formats[generation]
            if time.time() - timestamp < FORMAT_CACHE_TIMEOUT:
                logger.debug(f"Using cached format list for {generation}")
                return formats_set

        logger.info(f"🔍 Discovering available formats for {generation}...")

        # Try priority formats first (for common Pokemon)
        discovered = set()
        session = await self.get_session()

        # Check priority formats first
        priority_tasks = []
        for fmt in PRIORITY_FORMATS:
            priority_tasks.append(self._check_format_exists(session, generation, fmt))

        priority_results = await asyncio.gather(*priority_tasks, return_exceptions=True)
        for fmt, exists in zip(PRIORITY_FORMATS, priority_results):
            if exists and not isinstance(exists, Exception):
                discovered.add(fmt)

        # Then check comprehensive list in parallel batches
        remaining_formats = [
            f for f in COMPREHENSIVE_FORMAT_LIST if f not in PRIORITY_FORMATS
        ]

        # Process in batches to avoid overwhelming the API
        batch_size = 10
        for i in range(0, len(remaining_formats), batch_size):
            batch = remaining_formats[i : i + batch_size]
            tasks = [
                self._check_format_exists(session, generation, fmt) for fmt in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for fmt, exists in zip(batch, results):
                if exists and not isinstance(exists, Exception):
                    discovered.add(fmt)

        # Cache the discovered formats
        self.discovered_formats[generation] = (discovered, time.time())
        self.format_discoveries += 1

        logger.info(
            f"✅ Discovered {len(discovered)} formats for {generation}: "
            f"{', '.join(sorted(discovered))}"
        )

        return discovered

    async def _check_format_exists(
        self, session: aiohttp.ClientSession, generation: str, format_id: str
    ) -> bool:
        """
        Check if a format exists by trying to fetch it

        Args:
            session: aiohttp session
            generation: Generation string
            format_id: Format identifier

        Returns:
            True if format exists (200 response), False otherwise
        """
        url = f"{self.base_url}/{generation}{format_id}.json"

        try:
            async with self._rate_limiter:
                async with session.head(url) as resp:  # HEAD request is faster
                    return resp.status == 200
        except Exception:
            return False

    @retry_on_error(max_retries=3)
    async def find_pokemon_in_generation(
        self, pokemon: str, generation: str
    ) -> Dict[str, Dict]:
        """
        Find a Pokemon across all formats in a generation

        Now uses dynamic format discovery!

        Args:
            pokemon: Pokemon name
            generation: Generation (e.g., 'gen9')

        Returns:
            Dictionary mapping format_id to sets data
        """
        # Check if we have cached tier locations for this pokemon
        tier_cache_key = f"tier_location:{generation}:{pokemon}"
        cached_tiers = self._get_cached(tier_cache_key)

        if cached_tiers:
            logger.info(f"Using cached tier locations for {pokemon} in {generation}")
            result = {}
            for tier in cached_tiers:
                sets = await self.get_sets(pokemon, generation, tier)
                if sets:
                    result[tier] = sets
            return result

        # Discover available formats for this generation
        available_formats = await self.discover_formats_for_generation(generation)

        if not available_formats:
            logger.warning(f"No formats discovered for {generation}")
            return {}

        logger.info(
            f"Searching for {pokemon} in {generation} across "
            f"{len(available_formats)} discovered formats"
        )

        # Search ALL discovered formats in parallel
        tasks = []
        for tier in available_formats:
            tasks.append(self._fetch_format(pokemon, generation, tier))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results
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
        """Internal method to fetch a specific format and find pokemon"""
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
            pokemon: Pokemon name
            generation: Generation (e.g., 'gen9', 'gen8')
            tier: Competitive tier (e.g., 'ou', 'uu', 'ubers')

        Returns:
            Dictionary of sets or None if not found
        """
        pokemon = pokemon.lower().strip().replace(" ", "-")
        generation = generation.lower().strip()
        tier = tier.lower().strip()

        format_id = f"{generation}{tier}"
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

                        # Search for Pokemon
                        for poke_name, sets in data.items():
                            if poke_name.lower().replace(" ", "-") == pokemon:
                                self._set_cache(cache_key, sets)
                                logger.info(f"Found sets for {pokemon} in {format_id}")
                                return sets

                        # Partial match
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

    # ... rest of the methods (get_pokemon_ev_yield, get_pokemon_sprite, etc.) stay the same ...
    # (keeping existing implementation for EV yield and sprites)

    @retry_on_error(max_retries=3)
    async def get_pokemon_ev_yield(self, pokemon: str) -> Optional[Dict]:
        """Fetch EV yield data from PokeAPI"""
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
        except Exception as e:
            logger.error(f"Error fetching EV yield for {pokemon}: {e}", exc_info=True)
            return None

    @retry_on_error(max_retries=3)
    async def get_pokemon_sprite(
        self, pokemon: str, shiny: bool = False, generation: int = 9
    ) -> Optional[Dict]:
        """Fetch Pokemon sprite from PokeAPI"""
        pokemon = pokemon.lower().strip().replace(" ", "-")
        cache_key = f"sprite:{pokemon}:{shiny}:{generation}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            session = await self.get_session()
            species_url = f"{POKEAPI_URL}/pokemon-species/{pokemon}"

            async with self._rate_limiter:
                async with session.get(species_url) as species_resp:
                    if species_resp.status == 200:
                        species_data = await species_resp.json()
                        gen_data = species_data.get("generation", {})
                        gen_url = gen_data.get("url", "")

                        try:
                            introduced_gen = int(gen_url.rstrip("/").split("/")[-1])
                        except (ValueError, IndexError):
                            introduced_gen = 1

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
                            sprite_url = sprites.get(
                                "front_shiny" if shiny else "front_default"
                            )
                        else:
                            gen_key = gen_map.get(generation)
                            if gen_key:
                                versions = sprites.get("versions", {})
                                gen_sprites = versions.get(gen_key, {})
                                game_keys = list(gen_sprites.keys())
                                if game_keys:
                                    for game_key in game_keys:
                                        game_sprite = gen_sprites[game_key]
                                        sprite_url = game_sprite.get(
                                            "front_shiny" if shiny else "front_default"
                                        )
                                        if sprite_url:
                                            break

                        if not sprite_url:
                            logger.debug(
                                f"No sprite found for {pokemon} (shiny={shiny}, gen={generation})"
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
        except Exception as e:
            logger.error(f"Error fetching sprite for {pokemon}: {e}", exc_info=True)
            return None

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.discovered_formats.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        self.format_discoveries = 0
        logger.info("Cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": MAX_CACHE_SIZE,
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "discovered_generations": len(self.discovered_formats),
            "format_discoveries": self.format_discoveries,
        }
