import logging
import asyncio
import aiohttp
import io
import json
from PIL import Image
from typing import Optional, Dict, Any
import urllib.parse
import re # Import re module for use in clean_movie_name_for_search
from bs4 import BeautifulSoup

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

            # Include year in search query if available for better accuracy
            search_query = f"{clean_name} {year}" if year else clean_name
            
            logger.info(f"🔍 Searching TMDB for movie: {search_query}")

            # Search for movie
            search_params = {
                'api_key': self.api_key,
                'query': search_query,
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

            # Include year in search query if available for better accuracy
            search_query = f"{clean_name} {year}" if year else clean_name
            
            logger.info(f"🔍 Searching TMDB for TV series: {search_query}")

            # Search for TV series
            search_params = {
                'api_key': self.api_key,
                'query': search_query,
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

    async def fetch_google_images(self, query: str, limit: int = 10) -> list:
        """Fetch images from Google Images search"""
        url = f"https://www.google.com/search?q={query}&tbm=isch&hl=en&safe=off"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/",
            "DNT": "1",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"Google search failed with status: {response.status}")
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    image_urls = []

                    for script in soup.find_all('script'):
                        if script.string:
                            matches = re.findall(r'\"(https?://[^\"]+\.(?:jpg|jpeg|png|webp))\"', script.string)
                            image_urls.extend(match for match in matches if match.startswith('http'))

                    for img in soup.find_all('img', {'data-src': True}):
                        image_urls.append(img['data-src'])

                    return list(set(image_urls))[:limit]
        except Exception as e:
            logger.error(f"❌ Error fetching Google images: {e}")
            return []

    async def search_google_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Search for poster using Google Images as fallback"""
        try:
            # Create search query
            search_type = "tv series" if is_series else "movie"
            search_query = f"{title} {year} {search_type} poster" if year else f"{title} {search_type} poster"
            
            logger.info(f"🔍 Searching Google Images for: {search_query}")
            
            # Get image URLs from Google
            image_urls = await self.fetch_google_images(search_query, limit=5)
            
            if not image_urls:
                logger.warning(f"❌ No images found on Google for: {search_query}")
                return None

            # Try to download and process the first valid image
            async with aiohttp.ClientSession() as session:
                for i, url in enumerate(image_urls):
                    try:
                        logger.info(f"📥 Trying Google image {i+1}/{len(image_urls)}: {url[:100]}...")
                        
                        async with session.get(url, timeout=10) as response:
                            if response.status != 200:
                                logger.warning(f"❌ Failed to download image {i+1}, status: {response.status}")
                                continue

                            image_data = await response.read()
                            
                            if len(image_data) < 5000:  # Skip very small images
                                logger.warning(f"❌ Image {i+1} too small: {len(image_data)} bytes")
                                continue

                            # Process and resize the image
                            processed_image = await self.process_and_resize_poster(image_data)
                            if processed_image:
                                logger.info(f"✅ Successfully processed Google image for: {title}")
                                return processed_image
                            else:
                                logger.warning(f"❌ Failed to process image {i+1}")
                                continue
                                
                    except Exception as e:
                        logger.warning(f"❌ Error processing Google image {i+1}: {e}")
                        continue

            logger.warning(f"❌ Failed to get valid poster from Google for: {title}")
            return None

        except Exception as e:
            logger.error(f"❌ Error in Google poster search: {e}")
            return None

    async def search_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Search for poster (movie or TV series) using TMDB API with Google fallback"""
        try:
            if is_series:
                # Try TV series search first
                poster_data = await self.search_tv_poster(title, year)
                if poster_data:
                    return poster_data

                # Fallback to movie search
                logger.info(f"🔄 TV search failed, trying movie search for: {title}")
                poster_data = await self.search_movie_poster(title, year)
                if poster_data:
                    return poster_data
                    
                # Final fallback to Google Images
                logger.info(f"🔄 TMDB searches failed, trying Google Images for: {title}")
                return await self.search_google_poster(title, year, is_series=True)
            else:
                # Try movie search first
                poster_data = await self.search_movie_poster(title, year)
                if poster_data:
                    return poster_data

                # Fallback to TV series search
                logger.info(f"🔄 Movie search failed, trying TV search for: {title}")
                poster_data = await self.search_tv_poster(title, year)
                if poster_data:
                    return poster_data
                    
                # Final fallback to Google Images
                logger.info(f"🔄 TMDB searches failed, trying Google Images for: {title}")
                return await self.search_google_poster(title, year, is_series=False)

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
        """Process and resize poster image to 1280x720 by cropping to fill"""
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
            target_ratio = target_width / target_height

            # Calculate original aspect ratio
            original_ratio = original_width / original_height

            if original_ratio > target_ratio:
                # Image is wider than target ratio - crop width
                new_height = original_height
                new_width = int(original_height * target_ratio)
                crop_x = (original_width - new_width) // 2
                crop_y = 0
            else:
                # Image is taller than target ratio - crop height
                new_width = original_width
                new_height = int(original_width / target_ratio)
                crop_x = 0
                crop_y = (original_height - new_height) // 2

            # Crop the image to the target aspect ratio
            cropped_image = image.crop((crop_x, crop_y, crop_x + new_width, crop_y + new_height))
            logger.info(f"🔲 Cropped to: {new_width}x{new_height}")

            # Resize to target dimensions
            final_image = cropped_image.resize((target_width, target_height), Image.Resampling.LANCZOS)

            logger.info(f"📏 Final poster size: {target_width}x{target_height}")

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