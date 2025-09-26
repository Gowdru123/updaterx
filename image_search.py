import logging
import asyncio
import aiohttp
import io
import json
from PIL import Image
from typing import Optional, Dict, Any
import urllib.parse
import re # Import re module for use in clean_movie_name_for_search

logger = logging.getLogger(__name__)

class TMDBPosterFetcher:
    def __init__(self):
        self.api_key = "7a3197fe409e74fbaf50f85b2bf4f64f"
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/original"

    async def search_movie_poster(self, movie_name: str, year: Optional[str] = None) -> Optional[bytes]:
        """Search for movie poster using TMDB API"""
        try:
            # Clean movie name for search
            clean_name = self.clean_movie_name_for_search(movie_name)

            logger.info(f"🔍 Searching TMDB for movie: {clean_name}")

            # Search for movie
            search_params = {
                'api_key': self.api_key,
                'query': clean_name,
                'language': 'en-US'
            }

            if year:
                search_params['year'] = year

            search_url = f"{self.base_url}/search/movie"

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=search_params) as response:
                    if response.status != 200:
                        logger.error(f"❌ TMDB search failed with status: {response.status}")
                        return None

                    data = await response.json()
                    results = data.get('results', [])

                    if not results:
                        logger.warning(f"❌ No movie found in TMDB for: {clean_name}")
                        return None

                    # Get the first result (most relevant)
                    movie = results[0]
                    poster_path = movie.get('poster_path')

                    if not poster_path:
                        logger.warning(f"❌ No poster available for movie: {movie.get('title', clean_name)}")
                        return None

                    logger.info(f"✅ Found movie: {movie.get('title')} ({movie.get('release_date', 'Unknown')})")

                    # Download and resize poster
                    poster_url = f"{self.image_base_url}{poster_path}"
                    return await self.download_and_resize_poster(session, poster_url)

        except Exception as e:
            logger.error(f"❌ Error searching TMDB for movie: {e}")
            return None

    async def search_tv_poster(self, series_name: str, year: Optional[str] = None) -> Optional[bytes]:
        """Search for TV series poster using TMDB API"""
        try:
            # Clean series name for search
            clean_name = self.clean_movie_name_for_search(series_name)

            logger.info(f"🔍 Searching TMDB for TV series: {clean_name}")

            # Search for TV series
            search_params = {
                'api_key': self.api_key,
                'query': clean_name,
                'language': 'en-US'
            }

            if year:
                search_params['first_air_date_year'] = year

            search_url = f"{self.base_url}/search/tv"

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=search_params) as response:
                    if response.status != 200:
                        logger.error(f"❌ TMDB TV search failed with status: {response.status}")
                        return None

                    data = await response.json()
                    results = data.get('results', [])

                    if not results:
                        logger.warning(f"❌ No TV series found in TMDB for: {clean_name}")
                        return None

                    # Get the first result (most relevant)
                    tv_series = results[0]
                    poster_path = tv_series.get('poster_path')

                    if not poster_path:
                        logger.warning(f"❌ No poster available for TV series: {tv_series.get('name', clean_name)}")
                        return None

                    logger.info(f"✅ Found TV series: {tv_series.get('name')} ({tv_series.get('first_air_date', 'Unknown')})")

                    # Download and resize poster
                    poster_url = f"{self.image_base_url}{poster_path}"
                    return await self.download_and_resize_poster(session, poster_url)

        except Exception as e:
            logger.error(f"❌ Error searching TMDB for TV series: {e}")
            return None

    async def search_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Search for poster (movie or TV series) using TMDB API"""
        try:
            if is_series:
                # Try TV series search first
                poster_data = await self.search_tv_poster(title, year)
                if poster_data:
                    return poster_data

                # Fallback to movie search
                logger.info(f"🔄 TV search failed, trying movie search for: {title}")
                return await self.search_movie_poster(title, year)
            else:
                # Try movie search first
                poster_data = await self.search_movie_poster(title, year)
                if poster_data:
                    return poster_data

                # Fallback to TV series search
                logger.info(f"🔄 Movie search failed, trying TV search for: {title}")
                return await self.search_tv_poster(title, year)

        except Exception as e:
            logger.error(f"❌ Error in search_poster: {e}")
            return None

    async def download_and_resize_poster(self, session: aiohttp.ClientSession, poster_url: str) -> Optional[bytes]:
        """Download poster from TMDB and resize it"""
        try:
            logger.info(f"📥 Downloading poster from: {poster_url[:100]}...")

            async with session.get(poster_url) as response:
                if response.status != 200:
                    logger.error(f"❌ Failed to download poster, status: {response.status}")
                    return None

                image_data = await response.read()

                if len(image_data) < 1024:  # Too small
                    logger.error(f"❌ Downloaded image too small: {len(image_data)} bytes")
                    return None

                # Process and resize the image
                processed_image = await self.process_and_resize_poster(image_data)
                return processed_image

        except Exception as e:
            logger.error(f"❌ Error downloading poster: {e}")
            return None

    async def process_and_resize_poster(self, image_data: bytes) -> Optional[bytes]:
        """Process and resize poster image to 1280x720"""
        try:
            # Open and validate image
            image = Image.open(io.BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')

            # Get original dimensions
            original_width, original_height = image.size
            logger.info(f"📐 Original poster size: {original_width}x{original_height}")

            # Target dimensions for poster display
            target_width, target_height = 1280, 720

            # Calculate scaling to fit within target while maintaining aspect ratio
            scale = min(target_width / original_width, target_height / original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)

            # Resize the image
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Create new image with target dimensions and center the poster
            final_image = Image.new('RGB', (target_width, target_height), (0, 0, 0))

            # Calculate position to center the image
            x = (target_width - new_width) // 2
            y = (target_height - new_height) // 2

            # Paste the resized image onto the final image
            final_image.paste(image, (x, y))

            logger.info(f"📏 Resized poster to: {target_width}x{target_height}")

            # Save processed image
            output = io.BytesIO()
            final_image.save(output, format='JPEG', quality=85, optimize=True)
            processed_data = output.getvalue()

            logger.info(f"✅ Processed poster: {len(processed_data)} bytes")
            return processed_data

        except Exception as e:
            logger.error(f"❌ Error processing poster: {e}")
            return None

    def clean_movie_name_for_search(self, movie_name: str) -> str:
        """Clean movie name for TMDB search"""
        cleaned = movie_name

        # Remove quality indicators
        cleaned = re.sub(r'\b(HDRip|CAMRip|WEBRip|DVDRip|BluRay|BRRip|HDCAM|TC|TS|HQ)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(720p|1080p|480p|360p|4K|2160p|HD|FHD|UHD)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove codecs and technical terms
        cleaned = re.sub(r'\b(x264|x265|HEVC|H\.264|H\.265|AAC|AC3|DTS)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove file size indicators
        cleaned = re.sub(r'\b\d+(\.\d+)?(GB|MB)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove brackets and parentheses content that might contain quality info
        cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)

        # Remove special characters and normalize spaces
        cleaned = re.sub(r'[._\-]+', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        logger.info(f"🧹 Cleaned '{movie_name}' -> '{cleaned}' for TMDB search")
        return cleaned

# Create global instance
tmdb_fetcher = TMDBPosterFetcher()

# For backward compatibility
poster_fetcher = tmdb_fetcher
image_search = tmdb_fetcher