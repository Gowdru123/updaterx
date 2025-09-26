import logging
import re
import asyncio
import aiohttp
import io
import random
import time
from PIL import Image
from typing import Optional, Dict, Any
import json

logger = logging.getLogger(__name__)

class PosterFetcher:
    def __init__(self):
        # User agents to rotate to avoid detection
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
        ]
        self.last_request_time = 0
        self.request_delay = 2  # Seconds between requests

    def get_random_headers(self):
        """Get random headers to avoid detection"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }

    async def search_movie_poster(self, movie_name: str, year: Optional[str] = None) -> Optional[bytes]:
        """Search for movie poster on Google Images"""
        try:
            # Rate limiting to avoid being blocked
            current_time = time.time()
            if current_time - self.last_request_time < self.request_delay:
                await asyncio.sleep(self.request_delay - (current_time - self.last_request_time))

            self.last_request_time = time.time()

            # Clean movie name for search
            clean_name = self.clean_movie_name_for_search(movie_name)

            # Create search query
            if year:
                search_query = f"{clean_name} {year} poster"
            else:
                search_query = f"{clean_name} poster"

            logger.info(f"🔍 Searching Google Images for: {search_query}")

            # Google Images search URL
            search_url = f"https://www.google.com/search?q={search_query}&tbm=isch&safe=active"

            headers = self.get_random_headers()

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers
            ) as session:
                try:
                    async with session.get(search_url) as response:
                        if response.status == 429:
                            logger.warning("⚠️ Rate limited by Google, waiting longer...")
                            await asyncio.sleep(10)
                            return None

                        if response.status != 200:
                            logger.warning(f"❌ Google search failed with status: {response.status}")
                            return None

                        html_content = await response.text()

                        # Extract image URLs from the search results
                        image_urls = self.extract_image_urls(html_content)

                        if not image_urls:
                            logger.warning(f"❌ No image URLs found for: {search_query}")
                            return None

                        logger.info(f"📸 Found {len(image_urls)} potential poster URLs")

                        # Try to download and validate each image
                        for i, img_url in enumerate(image_urls[:10]):  # Try first 10 images
                            try:
                                logger.info(f"🔄 Trying image {i+1}: {img_url[:100]}...")

                                # Add delay between image downloads
                                if i > 0:
                                    await asyncio.sleep(1)

                                poster_data = await self.download_and_validate_poster(
                                    session, img_url, movie_name, year
                                )

                                if poster_data:
                                    logger.info(f"✅ Successfully found poster for: {movie_name}")
                                    return poster_data

                            except Exception as e:
                                logger.warning(f"⚠️ Failed to process image {i+1}: {str(e)[:100]}")
                                continue

                        logger.warning(f"❌ No valid poster found for: {movie_name}")
                        return None

                except asyncio.TimeoutError:
                    logger.warning("⏰ Timeout while searching for poster")
                    return None
                except Exception as e:
                    logger.error(f"❌ Error during poster search: {e}")
                    return None

        except Exception as e:
            logger.error(f"❌ Error in search_movie_poster: {e}")
            return None

    def extract_image_urls(self, html_content: str) -> list:
        """Extract image URLs from Google Images search results"""
        try:
            image_urls = []

            # Method 1: Look for data-src attributes (common in Google Images)
            data_src_pattern = re.findall(r'data-src="([^"]+)"', html_content)
            for url in data_src_pattern:
                if self.is_valid_image_url(url):
                    image_urls.append(url)

            # Method 2: Look for regular src attributes in img tags
            src_pattern = re.findall(r'<img[^>]+src="([^"]+)"', html_content)
            for url in src_pattern:
                if self.is_valid_image_url(url) and url not in image_urls:
                    image_urls.append(url)

            # Method 3: Look for JSON data containing image URLs
            json_pattern = re.findall(r'\["(https://[^"]+\.(?:jpg|jpeg|png|webp))[^"]*"', html_content)
            for url in json_pattern:
                if self.is_valid_image_url(url) and url not in image_urls:
                    image_urls.append(url)

            # Filter and sort by quality indicators
            filtered_urls = []
            for url in image_urls[:50]:  # Limit to first 50 URLs
                # Prefer larger images and movie poster sites
                if any(indicator in url.lower() for indicator in ['large', 'original', 'poster', 'movie', 'imdb', 'tmdb']):
                    filtered_urls.insert(0, url)  # Priority URLs at front
                else:
                    filtered_urls.append(url)

            logger.info(f"📸 Extracted {len(filtered_urls)} image URLs from search results")
            return filtered_urls

        except Exception as e:
            logger.error(f"❌ Error extracting image URLs: {e}")
            return []

    def is_valid_image_url(self, url: str) -> bool:
        """Check if URL is a valid image URL"""
        if not url or len(url) < 10:
            return False

        # Must be HTTP(S) URL
        if not url.startswith(('http://', 'https://')):
            return False

        # Must have image extension or be from known image hosting
        image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
        image_hosts = ('images.', 'img.', 'static.', 'cdn.', 'photo.', 'poster.')

        url_lower = url.lower()
        has_extension = any(ext in url_lower for ext in image_extensions)
        has_image_host = any(host in url_lower for host in image_hosts)

        return has_extension or has_image_host

    async def download_and_validate_poster(self, session: aiohttp.ClientSession, 
                                         img_url: str, movie_name: str, 
                                         year: Optional[str] = None) -> Optional[bytes]:
        """Download image and validate it's a movie poster"""
        try:
            headers = self.get_random_headers()
            headers['Referer'] = 'https://www.google.com/'

            async with session.get(img_url, headers=headers) as response:
                if response.status != 200:
                    return None

                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                if not any(img_type in content_type for img_type in ['image/jpeg', 'image/png', 'image/webp']):
                    return None

                image_data = await response.read()

                # Validate image data
                if len(image_data) < 1024:  # Too small
                    return None

                # Process and validate the image
                processed_image = await self.process_and_validate_poster(
                    image_data, movie_name, year
                )

                return processed_image

        except Exception as e:
            logger.warning(f"⚠️ Failed to download image: {e}")
            return None

    async def process_and_validate_poster(self, image_data: bytes, 
                                        movie_name: str, year: Optional[str] = None) -> Optional[bytes]:
        """Process image and validate it looks like a movie poster"""
        try:
            # Open and validate image
            image = Image.open(io.BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')

            # Check image dimensions (posters are usually taller than wide)
            width, height = image.size

            # Skip very small images
            if width < 200 or height < 300:
                logger.info(f"❌ Image too small: {width}x{height}")
                return None

            # Skip very wide images (probably not posters)
            aspect_ratio = width / height
            if aspect_ratio > 1.5:  # Too wide for a poster
                logger.info(f"❌ Image too wide for poster: {width}x{height} (ratio: {aspect_ratio:.2f})")
                return None

            # Prefer portrait orientation (typical for movie posters)
            if height > width:  # Portrait - good for posters
                logger.info(f"✅ Good poster dimensions: {width}x{height} (portrait)")
            elif aspect_ratio <= 1.2:  # Nearly square - acceptable
                logger.info(f"✅ Acceptable poster dimensions: {width}x{height} (square-ish)")
            else:
                logger.info(f"⚠️ Unusual poster dimensions: {width}x{height}")

            # Resize to desired dimensions (1280x720 as requested)
            # But maintain aspect ratio and crop/pad as needed
            target_width, target_height = 1280, 720

            # Calculate scaling to fit within target while maintaining aspect ratio
            scale = min(target_width / width, target_height / height)
            new_width = int(width * scale)
            new_height = int(height * scale)

            # Resize the image
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # If image is smaller than target, pad it; if larger, crop it
            if new_width != target_width or new_height != target_height:
                # Create new image with target dimensions
                final_image = Image.new('RGB', (target_width, target_height), (0, 0, 0))

                # Calculate position to center the image
                x = (target_width - new_width) // 2
                y = (target_height - new_height) // 2

                # Paste the resized image onto the final image
                final_image.paste(image, (x, y))
                image = final_image

            logger.info(f"📏 Resized poster to: {image.size}")

            # Save processed image
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=85, optimize=True)
            processed_data = output.getvalue()

            logger.info(f"✅ Processed poster: {len(processed_data)} bytes")
            return processed_data

        except Exception as e:
            logger.error(f"❌ Error processing poster: {e}")
            return None

    def clean_movie_name_for_search(self, movie_name: str) -> str:
        """Clean movie name for Google search"""
        cleaned = movie_name

        # Remove quality indicators
        cleaned = re.sub(r'\b(HDRip|CAMRip|WEBRip|DVDRip|BluRay|BRRip|HDCAM|TC|TS|HQ)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(720p|1080p|480p|360p|4K|2160p|HD|FHD|UHD)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove codecs and technical terms
        cleaned = re.sub(r'\b(x264|x265|HEVC|H\.264|H\.265|AAC|AC3|DTS)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove file size indicators
        cleaned = re.sub(r'\b\d+(\.\d+)?(GB|MB)\b', '', cleaned, flags=re.IGNORECASE)

        # Remove brackets and parentheses content
        cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)

        # Remove special characters and normalize spaces
        cleaned = re.sub(r'[._\-]+', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        logger.info(f"🧹 Cleaned '{movie_name}' -> '{cleaned}' for Google search")
        return cleaned

    async def search_google_images_poster(self, search_query: str) -> Optional[bytes]:
        """Search for movie poster using Google Images with the provided search query"""
        try:
            logger.info(f"🔍 Searching Google Images with query: {search_query}")

            # Rate limiting to avoid being blocked
            current_time = time.time()
            if current_time - self.last_request_time < self.request_delay:
                await asyncio.sleep(self.request_delay - (current_time - self.last_request_time))

            self.last_request_time = time.time()

            # Google Images search URL
            search_url = f"https://www.google.com/search?q={search_query}&tbm=isch&safe=active"

            headers = self.get_random_headers()

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers
            ) as session:
                try:
                    async with session.get(search_url) as response:
                        if response.status == 429:
                            logger.warning("⚠️ Rate limited by Google, waiting longer...")
                            await asyncio.sleep(10)
                            return None

                        if response.status != 200:
                            logger.warning(f"❌ Google search failed with status: {response.status}")
                            return None

                        html_content = await response.text()

                        # Extract image URLs from the search results
                        image_urls = self.extract_image_urls(html_content)

                        if not image_urls:
                            logger.warning(f"❌ No image URLs found for query: {search_query}")
                            return None

                        logger.info(f"📸 Found {len(image_urls)} potential poster URLs")

                        # Try to download and validate each image
                        for i, img_url in enumerate(image_urls[:10]):  # Try first 10 images
                            try:
                                logger.info(f"🔄 Trying image {i+1}: {img_url[:100]}...")

                                # Add delay between image downloads
                                if i > 0:
                                    await asyncio.sleep(1)

                                poster_data = await self.download_and_validate_poster(
                                    session, img_url, "", ""
                                )

                                if poster_data:
                                    logger.info(f"✅ Successfully found poster for query: {search_query}")
                                    return poster_data

                            except Exception as e:
                                logger.warning(f"⚠️ Failed to process image {i+1}: {str(e)[:100]}")
                                continue

                        logger.warning(f"❌ No valid poster found for query: {search_query}")
                        return None

                except asyncio.TimeoutError:
                    logger.warning("⏰ Timeout while searching for poster")
                    return None
                except Exception as e:
                    logger.error(f"❌ Error during poster search: {e}")
                    return None

        except Exception as e:
            logger.error(f"❌ Error in search_google_images_poster: {e}")
            return None

# Create global instance
poster_fetcher = PosterFetcher()
image_search = poster_fetcher  # For backward compatibility