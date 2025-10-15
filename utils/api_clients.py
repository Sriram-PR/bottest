import logging
import time
from typing import Any, Dict, Optional

import aiohttp

from config.settings import CACHE_TIMEOUT, SMOGON_SETS_URL

logger = logging.getLogger("smogon_bot.api")


class SmogonAPIClient:
    """Client for fetching competitive sets from Smogon"""

    def __init__(self):
        self.base_url = SMOGON_SETS_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, tuple[Any, float]] = {}  # {key: (data, timestamp)}

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
        """Get data from cache if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < CACHE_TIMEOUT:
                logger.debug(f"Cache hit for {key}")
                return data
            else:
                # Remove expired cache
                del self.cache[key]
        return None

    def _set_cache(self, key: str, data: Any):
        """Store data in cache with timestamp"""
        self.cache[key] = (data, time.time())
        logger.debug(f"Cached data for {key}")

    async def get_sets(
        self, pokemon: str, generation: str = "gen9", tier: str = "ou"
    ) -> Optional[Dict]:
        """
        Fetch competitive sets from Smogon

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
