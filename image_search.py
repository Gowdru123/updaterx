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

    async def fetch_google_images(self, query: str, limit: int = 15) -> list:
        """Fetch images from Google Images search with IMDB prioritization"""
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
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        logger.error(f"Google search failed with status: {response.status}")
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    all_image_urls = []
                    imdb_urls = []
                    high_quality_urls = []
                    regular_urls = []

                    # Extract image URLs from various sources
                    # Method 1: From script tags containing JSON data
                    for script in soup.find_all('script'):
                        if script.string and 'data:image' not in script.string:
                            # Look for high-resolution image URLs
                            matches = re.findall(r'\"(https?://[^\"]+\.(?:jpg|jpeg|png|webp))\"', script.string)
                            for match in matches:
                                if match.startswith('http') and len(match) > 50:  # Filter out very short URLs
                                    all_image_urls.append(match)

                    # Method 2: From img tags with data-src
                    for img in soup.find_all('img', {'data-src': True}):
                        src = img.get('data-src')
                        if src and src.startswith('http') and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            all_image_urls.append(src)

                    # Method 3: From img tags with src
                    for img in soup.find_all('img', {'src': True}):
                        src = img.get('src')
                        if src and src.startswith('http') and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            if 'data:image' not in src and len(src) > 50:  # Skip data URLs and very short URLs
                                all_image_urls.append(src)

                    # Remove duplicates while preserving order
                    seen_urls = set()
                    unique_urls = []
                    for url in all_image_urls:
                        if url not in seen_urls:
                            seen_urls.add(url)
                            unique_urls.append(url)

                    # Categorize URLs by priority
                    for url in unique_urls:
                        url_lower = url.lower()
                        
                        # Highest priority: IMDB images
                        if 'imdb.com' in url_lower or 'media-amazon.com' in url_lower:
                            imdb_urls.append(url)
                            logger.info(f"🎯 Found IMDB poster URL: {url[:100]}...")
                        
                        # High priority: High-quality indicators
                        elif any(indicator in url_lower for indicator in ['original', 'large', 'high', 'w1280', 'w780', 'poster']):
                            high_quality_urls.append(url)
                        
                        # Regular URLs
                        else:
                            regular_urls.append(url)

                    # Return prioritized list: IMDB first, then high quality, then regular
                    prioritized_urls = imdb_urls + high_quality_urls + regular_urls
                    
                    logger.info(f"📊 Google image search results: {len(imdb_urls)} IMDB, {len(high_quality_urls)} high-quality, {len(regular_urls)} regular")
                    
                    return prioritized_urls[:limit]

        except Exception as e:
            logger.error(f"❌ Error fetching Google images: {e}")
            return []

    async def search_google_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Search for poster using Google Images as fallback with IMDB prioritization"""
        try:
            search_type = "tv series" if is_series else "movie"
            
            # Try multiple search queries for better results
            search_queries = [
                f"{title} {year} {search_type} poster imdb" if year else f"{title} {search_type} poster imdb",
                f"{title} {year} poster" if year else f"{title} poster",
                f"{title} {search_type} poster high resolution" if not year else f"{title} {year} poster high resolution"
            ]
            
            for query_idx, search_query in enumerate(search_queries):
                logger.info(f"🔍 Google search attempt {query_idx + 1}: {search_query}")
                
                # Get image URLs from Google
                image_urls = await self.fetch_google_images(search_query, limit=10)
                
                if not image_urls:
                    logger.warning(f"❌ No images found for query: {search_query}")
                    continue

                # Try to download and process images
                async with aiohttp.ClientSession() as session:
                    for i, url in enumerate(image_urls):
                        try:
                            # Skip obviously bad URLs
                            if any(bad in url.lower() for bad in ['favicon', 'logo', 'icon', 'thumb']):
                                continue
                                
                            url_type = "IMDB" if ('imdb.com' in url.lower() or 'media-amazon.com' in url.lower()) else "Regular"
                            logger.info(f"📥 Trying {url_type} image {i+1}/{len(image_urls)}: {url[:120]}...")
                            
                            # Set timeout based on priority
                            timeout = 15 if url_type == "IMDB" else 10
                            
                            async with session.get(url, timeout=timeout, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                "Referer": "https://www.google.com/"
                            }) as response:
                                if response.status != 200:
                                    logger.warning(f"❌ Failed to download {url_type} image {i+1}, status: {response.status}")
                                    continue

                                image_data = await response.read()
                                
                                # More lenient size check for IMDB images
                                min_size = 3000 if url_type == "IMDB" else 5000
                                if len(image_data) < min_size:
                                    logger.warning(f"❌ {url_type} image {i+1} too small: {len(image_data)} bytes")
                                    continue

                                # Validate it's actually an image
                                try:
                                    from PIL import Image
                                    test_image = Image.open(io.BytesIO(image_data))
                                    width, height = test_image.size
                                    
                                    # Skip very small or very wide/tall images
                                    if width < 200 or height < 200 or width/height > 3 or height/width > 3:
                                        logger.warning(f"❌ {url_type} image {i+1} has bad dimensions: {width}x{height}")
                                        continue
                                        
                                except Exception as img_e:
                                    logger.warning(f"❌ {url_type} image {i+1} validation failed: {img_e}")
                                    continue

                                # Process and resize the image
                                processed_image = await self.process_and_resize_poster(image_data)
                                if processed_image:
                                    logger.info(f"✅ Successfully processed {url_type} Google image for: {title}")
                                    return processed_image
                                else:
                                    logger.warning(f"❌ Failed to process {url_type} image {i+1}")
                                    continue
                                    
                        except asyncio.TimeoutError:
                            logger.warning(f"❌ Timeout downloading image {i+1}")
                            continue
                        except Exception as e:
                            logger.warning(f"❌ Error processing image {i+1}: {e}")
                            continue

                logger.info(f"❌ No valid images found with query: {search_query}")

            logger.warning(f"❌ Failed to get valid poster from Google for: {title}")
            return None

        except Exception as e:
            logger.error(f"❌ Error in Google poster search: {e}")
            return None

    async def search_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Search for poster prioritizing Google IMDB search first, then TMDB as fallback"""
        try:
            # Try Google Images first (prioritizes IMDB results)
            logger.info(f"🔍 Starting with Google IMDB search for: {title}")
            poster_data = await self.search_google_poster(title, year, is_series)
            if poster_data:
                logger.info(f"✅ Found poster via Google IMDB search for: {title}")
                return poster_data

            logger.info(f"🔄 Google search failed, trying TMDB for: {title}")
            
            if is_series:
                # Try TV series search
                poster_data = await self.search_tv_poster(title, year)
                if poster_data:
                    logger.info(f"✅ Found poster via TMDB TV search for: {title}")
                    return poster_data

                # Fallback to movie search
                logger.info(f"🔄 TMDB TV search failed, trying TMDB movie search for: {title}")
                poster_data = await self.search_movie_poster(title, year)
                if poster_data:
                    logger.info(f"✅ Found poster via TMDB movie search for: {title}")
                    return poster_data
            else:
                # Try movie search
                poster_data = await self.search_movie_poster(title, year)
                if poster_data:
                    logger.info(f"✅ Found poster via TMDB movie search for: {title}")
                    return poster_data

                # Fallback to TV series search
                logger.info(f"🔄 TMDB movie search failed, trying TMDB TV search for: {title}")
                poster_data = await self.search_tv_poster(title, year)
                if poster_data:
                    logger.info(f"✅ Found poster via TMDB TV search for: {title}")
                    return poster_data
            
            logger.warning(f"❌ All poster search methods failed for: {title}")
            return None

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
        """Process and resize poster image to fit within 1280x720 while maintaining aspect ratio"""
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

            # Calculate new dimensions to fit within target while maintaining aspect ratio
            if original_ratio > target_ratio:
                # Image is wider - fit by width
                new_width = target_width
                new_height = int(target_width / original_ratio)
            else:
                # Image is taller - fit by height
                new_height = target_height
                new_width = int(target_height * original_ratio)

            logger.info(f"📏 Fitted dimensions: {new_width}x{new_height}")

            # Resize image to fitted dimensions
            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Create a black background canvas with target dimensions
            final_image = Image.new('RGB', (target_width, target_height), (0, 0, 0))

            # Calculate position to center the resized image
            paste_x = (target_width - new_width) // 2
            paste_y = (target_height - new_height) // 2

            # Paste the resized image onto the center of the black canvas
            final_image.paste(resized_image, (paste_x, paste_y))

            logger.info(f"📏 Final poster size: {target_width}x{target_height} with image centered")

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