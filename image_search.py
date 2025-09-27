` tags.

<replit_final_file>
import logging
import asyncio
import aiohttp
import io
import json
from PIL import Image
from typing import Optional, Dict, Any
import urllib.parse
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class TMDBImageSearch:
    def __init__(self):
        self.api_key = "8265bd1679663a7ea12ac168da84d2e8"  # Free TMDB API key
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/w500"

    def clean_movie_name_for_search(self, movie_name: str) -> str:
        """Clean movie name for better TMDB search results"""
        cleaned = movie_name.strip()

        # Remove common prefixes/suffixes that might interfere
        prefixes_to_remove = ['The ', 'A ', 'An ']
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]

        # Remove year if present
        cleaned = re.sub(r'\b(19|20)\d{2}\b', '', cleaned)

        # Remove quality indicators
        cleaned = re.sub(r'\b(720p|1080p|480p|HDRip|BluRay|WEBRip|CAM|TS|TC)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove file size indicators
        cleaned = re.sub(r'\b\d+(\.\d+)?(GB|MB)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove brackets and parentheses content that might contain quality info
        cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)

        # Remove special characters and normalize spaces
        cleaned = re.sub(r'[._\-]+', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        logger.info(f"🧹 Cleaned '{movie_name}' -> '{cleaned}' for TMDB search")
        return cleaned

    async def search_poster(self, movie_name: str, year: str = None, is_series: bool = False) -> Optional[bytes]:
        """Search for movie/series poster using TMDB API"""
        try:
            clean_name = self.clean_movie_name_for_search(movie_name)

            if not clean_name:
                logger.warning(f"Empty search term after cleaning: {movie_name}")
                return None

            # Choose endpoint based on content type
            endpoint = "search/tv" if is_series else "search/movie"

            # Build search URL
            params = {
                'api_key': self.api_key,
                'query': clean_name,
                'language': 'en-US'
            }

            if year and not is_series:
                params['year'] = year
            elif year and is_series:
                params['first_air_date_year'] = year

            search_url = f"{self.base_url}/{endpoint}"

            logger.info(f"🔍 Searching TMDB: {search_url} with params: {params}")

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"TMDB API error: {response.status}")
                        return None

                    data = await response.json()
                    results = data.get('results', [])

                    if not results:
                        logger.warning(f"No TMDB results found for: {clean_name}")
                        return None

                    # Get the first result
                    first_result = results[0]
                    poster_path = first_result.get('poster_path')

                    if not poster_path:
                        logger.warning(f"No poster available for: {clean_name}")
                        return None

                    # Download the poster
                    poster_url = f"{self.image_base_url}{poster_path}"
                    logger.info(f"📸 Downloading poster from: {poster_url}")

                    async with session.get(poster_url) as poster_response:
                        if poster_response.status == 200:
                            poster_data = await poster_response.read()

                            # Optimize image size
                            try:
                                img = Image.open(io.BytesIO(poster_data))
                                if img.size[0] > 500:  # Resize if too large
                                    img.thumbnail((500, 750), Image.Resampling.LANCZOS)

                                output = io.BytesIO()
                                img.save(output, format='JPEG', quality=85, optimize=True)
                                optimized_data = output.getvalue()

                                logger.info(f"✅ Successfully downloaded and optimized poster for: {movie_name}")
                                return optimized_data
                            except Exception as e:
                                logger.error(f"Error optimizing image: {e}")
                                return poster_data
                        else:
                            logger.error(f"Failed to download poster: {poster_response.status}")
                            return None

        except Exception as e:
            logger.error(f"Error searching for poster: {e}")
            return None

# Create global instance
image_search = TMDBImageSearch()