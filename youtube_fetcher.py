
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
            # Clean movie name for better search results
            clean_name = self.clean_movie_name_for_search(movie_name)
            
            # Create comprehensive search queries
            search_terms = [
                f"{clean_name} official trailer",
                f"{clean_name} trailer official",
                f"{clean_name} movie trailer",
                f"{clean_name} film trailer",
                f"{clean_name} teaser trailer"
            ]
            
            # Add year variants if available
            if year:
                year_terms = [
                    f"{clean_name} {year} official trailer",
                    f"{clean_name} {year} trailer",
                    f"{clean_name} {year} movie trailer"
                ]
                search_terms = year_terms + search_terms
            
            # Also try original name if cleaning changed it significantly
            if clean_name.lower() != movie_name.lower():
                original_terms = [
                    f"{movie_name} official trailer",
                    f"{movie_name} trailer"
                ]
                if year:
                    original_terms.insert(0, f"{movie_name} {year} trailer")
                search_terms.extend(original_terms)
            
            logger.info(f"🔍 Searching YouTube for: {clean_name} (year: {year})")
            logger.info(f"🔍 Search terms: {search_terms[:3]}...")  # Log first 3 terms
            
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
        cleaned = movie_name
        
        # Remove quality indicators
        cleaned = re.sub(r'\b(HDRip|CAMRip|WEBRip|DVDRip|BluRay|BRRip|HDCAM|TC|TS)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(720p|1080p|480p|360p|4K|2160p|HD|FHD|UHD)\b', '', cleaned, flags=re.IGNORECASE)
        
        # Remove codecs and technical terms
        cleaned = re.sub(r'\b(x264|x265|HEVC|H\.264|H\.265|AAC|AC3|DTS)\b', '', cleaned, flags=re.IGNORECASE)
        
        # Remove language indicators (but keep for regional cinema search)
        # cleaned = re.sub(r'\b(Hindi|Tamil|Telugu|Kannada|Malayalam|English|Dubbed)\b', '', cleaned, flags=re.IGNORECASE)
        
        # Remove file size indicators
        cleaned = re.sub(r'\b\d+(\.\d+)?(GB|MB)\b', '', cleaned, flags=re.IGNORECASE)
        
        # Remove brackets and parentheses content that might contain technical info
        cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)
        
        # Remove special characters and normalize spaces
        cleaned = re.sub(r'[._\-]+', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Capitalize properly for better search
        cleaned = ' '.join(word.capitalize() for word in cleaned.split())
        
        logger.info(f"🧹 Cleaned '{movie_name}' -> '{cleaned}' for YouTube search")
        return cleaned

# Create global instance
youtube_fetcher = YouTubeFetcher()
