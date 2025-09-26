
import logging
import re
import asyncio
import aiohttp
import yt_dlp
from PIL import Image
import io
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class YouTubeFetcher:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'best[height<=720]',  # Limit quality for faster processing
        }

    async def search_movie_trailer(self, movie_name: str, year: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search for official movie trailer on YouTube"""
        try:
            # Create search query - prioritize official trailers
            search_terms = [
                f"{movie_name} official trailer",
                f"{movie_name} trailer official", 
                f"{movie_name} movie trailer"
            ]
            
            if year:
                search_terms = [f"{term} {year}" for term in search_terms]
            
            logger.info(f"🔍 Searching YouTube for: {movie_name}")
            
            for search_query in search_terms:
                try:
                    # Use yt-dlp to search YouTube
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': True,
                        'default_search': 'ytsearch5:'  # Get top 5 results
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        search_results = ydl.extract_info(search_query, download=False)
                        
                        if search_results and 'entries' in search_results:
                            # Filter for official trailers
                            for entry in search_results['entries']:
                                if entry and 'id' in entry:
                                    title = entry.get('title', '').lower()
                                    uploader = entry.get('uploader', '').lower()
                                    
                                    # Check if it's likely an official trailer
                                    is_official = any(keyword in title for keyword in [
                                        'official trailer', 'trailer official', 'official teaser',
                                        'movie trailer', 'film trailer'
                                    ])
                                    
                                    # Check for official channels/studios
                                    is_official_channel = any(keyword in uploader for keyword in [
                                        'official', 'studios', 'entertainment', 'pictures',
                                        'films', 'cinema', 'movie'
                                    ])
                                    
                                    if is_official or is_official_channel:
                                        logger.info(f"✅ Found official trailer: {entry.get('title')}")
                                        return {
                                            'id': entry['id'],
                                            'title': entry.get('title'),
                                            'uploader': entry.get('uploader'),
                                            'url': f"https://youtube.com/watch?v={entry['id']}"
                                        }
                            
                            # If no official found, return first result
                            if search_results['entries']:
                                entry = search_results['entries'][0]
                                logger.info(f"⚠️ Using first result: {entry.get('title')}")
                                return {
                                    'id': entry['id'],
                                    'title': entry.get('title'),
                                    'uploader': entry.get('uploader'),
                                    'url': f"https://youtube.com/watch?v={entry['id']}"
                                }
                
                except Exception as e:
                    logger.warning(f"Search attempt failed for '{search_query}': {e}")
                    continue
            
            logger.warning(f"❌ No trailer found for: {movie_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching for trailer: {e}")
            return None

    async def get_video_thumbnail(self, video_id: str) -> Optional[bytes]:
        """Get video thumbnail from YouTube"""
        try:
            # YouTube thumbnail URLs - try different qualities
            thumbnail_urls = [
                f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",  # Best quality
                f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",     # High quality
                f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",     # Medium quality
                f"https://img.youtube.com/vi/{video_id}/sddefault.jpg"      # Standard quality
            ]
            
            async with aiohttp.ClientSession() as session:
                for url in thumbnail_urls:
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                thumbnail_data = await response.read()
                                
                                # Verify it's a valid image
                                try:
                                    Image.open(io.BytesIO(thumbnail_data))
                                    logger.info(f"✅ Downloaded thumbnail from: {url}")
                                    return thumbnail_data
                                except Exception:
                                    continue
                    except Exception as e:
                        logger.warning(f"Failed to download from {url}: {e}")
                        continue
            
            logger.warning(f"❌ Could not download thumbnail for video: {video_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting thumbnail: {e}")
            return None

    async def process_thumbnail(self, thumbnail_data: bytes) -> Optional[bytes]:
        """Process thumbnail image - resize and optimize for Telegram"""
        try:
            # Open image
            image = Image.open(io.BytesIO(thumbnail_data))
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            
            # Resize if too large (Telegram limits)
            max_size = (1280, 720)  # HD resolution
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                logger.info(f"📏 Resized image to: {image.size}")
            
            # Save processed image
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=85, optimize=True)
            processed_data = output.getvalue()
            
            logger.info(f"✅ Processed thumbnail: {len(processed_data)} bytes")
            return processed_data
            
        except Exception as e:
            logger.error(f"Error processing thumbnail: {e}")
            return None

    def clean_movie_name_for_search(self, movie_name: str) -> str:
        """Clean movie name for better YouTube search results"""
        # Remove common unwanted patterns
        cleaned = re.sub(r'\b(HDRip|CAMRip|WEBRip|DVDRip|BluRay|BRRip)\b', '', movie_name, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(720p|1080p|480p|360p|4K|2160p)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(x264|x265|HEVC|H\.264|H\.265)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(Hindi|Tamil|Telugu|Kannada|Malayalam|English)\b', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra spaces and return
        return re.sub(r'\s+', ' ', cleaned).strip()

# Create global instance
youtube_fetcher = YouTubeFetcher()
