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

    async def search_direct_imdb_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Method 1: Direct IMDB poster search with enhanced extraction"""
        try:
            search_type = "tv" if is_series else "title"
            search_query = f"{title} {year}" if year else title
            
            # Enhanced IMDB search URLs
            imdb_search_urls = [
                f"https://www.imdb.com/find?q={urllib.parse.quote(search_query)}&s={search_type}",
                f"https://www.imdb.com/find?q={urllib.parse.quote(title)}&s=all"
            ]
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1",
                "Connection": "keep-alive",
            }

            async with aiohttp.ClientSession() as session:
                for url in imdb_search_urls:
                    try:
                        logger.info(f"🎬 Direct IMDB search: {url}")
                        
                        async with session.get(url, headers=headers, timeout=15) as response:
                            if response.status != 200:
                                continue
                                
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Look for poster images in IMDB results
                            poster_urls = []
                            
                            # Method 1: Find images in search results
                            for img in soup.find_all('img'):
                                src = img.get('src') or img.get('data-src')
                                if src and ('media-amazon.com' in src or 'imdb.com' in src):
                                    if any(x in src.lower() for x in ['poster', 'primary', 'image']):
                                        # Convert to high resolution
                                        if '_V1_' in src:
                                            high_res_url = re.sub(r'_V1_.*?\.jpg', '_V1_FMjpg_UX1000_.jpg', src)
                                            poster_urls.append(high_res_url)
                                        poster_urls.append(src)
                            
                            # Method 2: Extract from JSON-LD or script tags
                            for script in soup.find_all('script', type='application/ld+json'):
                                try:
                                    data = json.loads(script.string)
                                    if 'image' in data and isinstance(data['image'], str):
                                        poster_urls.append(data['image'])
                                except:
                                    pass
                            
                            # Try downloading posters
                            for poster_url in poster_urls[:5]:  # Try top 5
                                try:
                                    logger.info(f"📥 Trying IMDB poster: {poster_url[:100]}...")
                                    
                                    async with session.get(poster_url, headers=headers, timeout=12) as img_response:
                                        if img_response.status == 200:
                                            image_data = await img_response.read()
                                            
                                            if len(image_data) > 5000:  # Minimum size check
                                                processed_image = await self.process_and_resize_poster(image_data)
                                                if processed_image:
                                                    logger.info(f"✅ Direct IMDB poster found for: {title}")
                                                    return processed_image
                                except Exception as e:
                                    logger.warning(f"❌ Failed to download IMDB poster: {e}")
                                    continue
                                    
                    except Exception as e:
                        logger.warning(f"❌ IMDB search failed: {e}")
                        continue
                        
            return None
            
        except Exception as e:
            logger.error(f"❌ Error in direct IMDB search: {e}")
            return None

    async def search_amazon_prime_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Method 2: Amazon Prime Video poster search with enhanced extraction"""
        try:
            search_query = f"{title} {year}" if year else title
            
            # Amazon Prime search URLs
            amazon_urls = [
                f"https://www.amazon.com/s?k={urllib.parse.quote(search_query)}&i=prime-instant-video",
                f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={urllib.parse.quote(search_query)}",
            ]
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1",
                "Connection": "keep-alive",
            }

            async with aiohttp.ClientSession() as session:
                for url in amazon_urls:
                    try:
                        logger.info(f"📺 Amazon Prime search: {url}")
                        
                        async with session.get(url, headers=headers, timeout=15) as response:
                            if response.status != 200:
                                continue
                                
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Look for Amazon poster images
                            poster_urls = []
                            
                            # Method 1: Find images with Amazon media URLs
                            for img in soup.find_all('img'):
                                src = img.get('src') or img.get('data-src')
                                if src and ('amazon.com' in src or 'amazonaws.com' in src):
                                    if any(x in src.lower() for x in ['poster', 'image', 'cover']):
                                        # Convert to high resolution
                                        if 'images-amazon.com' in src or 'm.media-amazon.com' in src:
                                            high_res_url = re.sub(r'\._.*?_\.', '._SY1000_CR0,0,675,1000_.', src)
                                            poster_urls.append(high_res_url)
                                        poster_urls.append(src)
                            
                            # Method 2: Look for specific Amazon poster patterns
                            for img in soup.find_all('img', class_=re.compile(r'.*image.*|.*poster.*')):
                                src = img.get('src') or img.get('data-src')
                                if src and 'amazon' in src:
                                    poster_urls.append(src)
                            
                            # Try downloading posters
                            for poster_url in poster_urls[:5]:  # Try top 5
                                try:
                                    logger.info(f"📥 Trying Amazon poster: {poster_url[:100]}...")
                                    
                                    async with session.get(poster_url, headers=headers, timeout=12) as img_response:
                                        if img_response.status == 200:
                                            image_data = await img_response.read()
                                            
                                            if len(image_data) > 5000:  # Minimum size check
                                                processed_image = await self.process_and_resize_poster(image_data)
                                                if processed_image:
                                                    logger.info(f"✅ Amazon Prime poster found for: {title}")
                                                    return processed_image
                                except Exception as e:
                                    logger.warning(f"❌ Failed to download Amazon poster: {e}")
                                    continue
                                    
                    except Exception as e:
                        logger.warning(f"❌ Amazon search failed: {e}")
                        continue
                        
            return None
            
        except Exception as e:
            logger.error(f"❌ Error in Amazon Prime search: {e}")
            return None

    async def search_enhanced_google_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Method 3: Enhanced Google search with multiple strategies"""
        try:
            search_type = "tv series" if is_series else "movie"
            
            # Multiple enhanced search strategies
            search_queries = [
                f'site:imdb.com "{title}" {year} poster' if year else f'site:imdb.com "{title}" poster',
                f'site:media-amazon.com "{title}" poster',
                f'"{title}" {year} poster high resolution imdb' if year else f'"{title}" poster high resolution imdb',
                f'"{title}" {year} {search_type} poster site:imdb.com OR site:amazon.com' if year else f'"{title}" {search_type} poster site:imdb.com OR site:amazon.com',
                f'"{title}" poster filetype:jpg OR filetype:png imdb'
            ]
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
                "DNT": "1",
            }
            
            async with aiohttp.ClientSession() as session:
                for query_idx, search_query in enumerate(search_queries):
                    try:
                        logger.info(f"🔍 Enhanced Google search {query_idx + 1}: {search_query}")
                        
                        google_url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}&tbm=isch&hl=en&safe=off"
                        
                        async with session.get(google_url, headers=headers, timeout=15) as response:
                            if response.status != 200:
                                continue
                                
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Enhanced image extraction
                            poster_urls = []
                            
                            # Method 1: Extract from JSON data in scripts
                            for script in soup.find_all('script'):
                                if script.string and 'data:image' not in script.string:
                                    # Look for IMDB and Amazon URLs specifically
                                    imdb_matches = re.findall(r'\"(https?://[^\"]*(?:imdb\.com|media-amazon\.com)[^\"]*\.(?:jpg|jpeg|png|webp))\"', script.string)
                                    for match in imdb_matches:
                                        if len(match) > 50:  # Filter out tiny URLs
                                            poster_urls.append(match)
                                    
                                    # Look for other high-quality image URLs
                                    other_matches = re.findall(r'\"(https?://[^\"]+\.(?:jpg|jpeg|png|webp))\"', script.string)
                                    for match in other_matches:
                                        if len(match) > 80 and any(keyword in match.lower() for keyword in ['poster', 'image', 'large', 'high']):
                                            poster_urls.append(match)
                            
                            # Method 2: Direct img tag extraction with prioritization
                            for img in soup.find_all('img'):
                                src = img.get('src') or img.get('data-src')
                                if src and src.startswith('http') and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                                    if 'data:image' not in src and len(src) > 50:
                                        # Prioritize IMDB and Amazon
                                        if any(domain in src.lower() for domain in ['imdb.com', 'media-amazon.com', 'amazon.com']):
                                            poster_urls.insert(0, src)  # Add to beginning
                                        else:
                                            poster_urls.append(src)
                            
                            # Remove duplicates while preserving order
                            seen_urls = set()
                            unique_poster_urls = []
                            for url in poster_urls:
                                if url not in seen_urls:
                                    seen_urls.add(url)
                                    unique_poster_urls.append(url)
                            
                            # Try downloading posters (prioritize IMDB/Amazon)
                            for i, poster_url in enumerate(unique_poster_urls[:10]):  # Try top 10
                                try:
                                    url_type = "Priority" if any(domain in poster_url.lower() for domain in ['imdb.com', 'media-amazon.com', 'amazon.com']) else "Regular"
                                    logger.info(f"📥 Trying {url_type} poster {i+1}: {poster_url[:120]}...")
                                    
                                    async with session.get(poster_url, headers=headers, timeout=12) as img_response:
                                        if img_response.status == 200:
                                            image_data = await img_response.read()
                                            
                                            if len(image_data) > 5000:  # Minimum size check
                                                # Validate image
                                                try:
                                                    test_image = Image.open(io.BytesIO(image_data))
                                                    width, height = test_image.size
                                                    
                                                    # Skip very small or very wide/tall images
                                                    if width >= 200 and height >= 200 and width/height <= 3 and height/width <= 3:
                                                        processed_image = await self.process_and_resize_poster(image_data)
                                                        if processed_image:
                                                            logger.info(f"✅ Enhanced Google poster found for: {title}")
                                                            return processed_image
                                                except Exception:
                                                    continue
                                        
                                except Exception as e:
                                    logger.warning(f"❌ Failed to download enhanced Google poster: {e}")
                                    continue
                                    
                    except Exception as e:
                        logger.warning(f"❌ Enhanced Google search failed: {e}")
                        continue
                        
            return None
            
        except Exception as e:
            logger.error(f"❌ Error in enhanced Google search: {e}")
            return None

    async def search_poster(self, title: str, year: Optional[str] = None, is_series: bool = False) -> Optional[bytes]:
        """Search for poster using 4 methods first, then TMDB as fallback"""
        try:
            logger.info(f"🎬 Starting poster search for: {title} ({year if year else 'No year'})")
            
            # Method 1: Direct IMDB poster search
            logger.info(f"🔍 Method 1: Direct IMDB search for: {title}")
            poster_data = await self.search_direct_imdb_poster(title, year, is_series)
            if poster_data:
                logger.info(f"✅ Found poster via Direct IMDB search for: {title}")
                return poster_data

            # Method 2: Amazon Prime poster search
            logger.info(f"🔍 Method 2: Amazon Prime search for: {title}")
            poster_data = await self.search_amazon_prime_poster(title, year, is_series)
            if poster_data:
                logger.info(f"✅ Found poster via Amazon Prime search for: {title}")
                return poster_data

            # Method 3: Enhanced Google search
            logger.info(f"🔍 Method 3: Enhanced Google search for: {title}")
            poster_data = await self.search_enhanced_google_poster(title, year, is_series)
            if poster_data:
                logger.info(f"✅ Found poster via Enhanced Google search for: {title}")
                return poster_data

            # Method 4: Original Google IMDB search
            logger.info(f"🔍 Method 4: Original Google IMDB search for: {title}")
            poster_data = await self.search_google_poster(title, year, is_series)
            if poster_data:
                logger.info(f"✅ Found poster via Original Google search for: {title}")
                return poster_data

            # Fallback: TMDB API search
            logger.info(f"🔄 All 4 methods failed, trying TMDB fallback for: {title}")
            
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

            # Resize image to exactly fill target dimensions (this will stretch the image)
            final_image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

            logger.info(f"📏 Final poster size: {target_width}x{target_height} (stretched to fill)")

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
