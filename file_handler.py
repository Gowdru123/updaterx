
import re
from typing import Dict, List, Set
from config import Config

class FileHandler:
    def __init__(self):
        self.config = Config()
    
    def is_video_file(self, filename: str) -> bool:
        """Check if file is a supported video format"""
        return any(filename.lower().endswith(ext) for ext in self.config.SUPPORTED_FORMATS)
    
    def extract_movie_details(self, filename: str) -> Dict:
        """Extract comprehensive movie details from filename"""
        if not self.is_video_file(filename):
            return None
        
        # Remove file extension
        name = re.sub(r'\.[^.]+$', '', filename)
        original_name = name
        
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', name)
        year = year_match.group() if year_match else None
        
        # Extract quality
        quality_pattern = '|'.join(self.config.QUALITY_PATTERNS)
        quality_matches = re.findall(f'({quality_pattern})', name, re.IGNORECASE)
        qualities = list(set([q.upper() for q in quality_matches])) if quality_matches else ['Unknown']
        
        # Extract language
        language_pattern = '|'.join(self.config.LANGUAGE_PATTERNS)
        language_matches = re.findall(f'({language_pattern})', name, re.IGNORECASE)
        languages = list(set([lang.capitalize() for lang in language_matches])) if language_matches else ['Unknown']
        
        # Extract size if present
        size_match = re.search(r'(\d+(?:\.\d+)?(?:GB|MB))', name, re.IGNORECASE)
        file_size = size_match.group(1) if size_match else None
        
        # Clean movie name
        clean_name = self.clean_movie_name(name)
        
        return {
            'original_filename': filename,
            'movie_name': clean_name,
            'year': year,
            'qualities': qualities,
            'languages': languages,
            'file_size': file_size,
            'raw_name': original_name
        }
    
    def clean_movie_name(self, name: str) -> str:
        """Clean and extract core movie name"""
        # Remove common patterns
        patterns_to_remove = [
            r'\b(19|20)\d{2}\b',  # Years
            r'\b(720p|1080p|480p|360p|4K|2K|HD|CAM|HDRip|DVDRip|BluRay|WEBRip|HDCAM|TC)\b',  # Quality
            r'\b(Hindi|English|Tamil|Telugu|Malayalam|Kannada|Bengali|Marathi|Gujarati|Punjabi|Urdu|Bhojpuri)\b',  # Languages
            r'\[.*?\]',  # Bracketed content
            r'\(.*?\)',  # Parentheses content
            r'\b\d+(?:\.\d+)?(?:GB|MB)\b',  # File sizes
            r'\bx264\b|\bx265\b|\bHEVC\b',  # Codecs
            r'\bAAC\b|\bAC3\b|\bDTS\b',  # Audio codecs
        ]
        
        clean_name = name
        for pattern in patterns_to_remove:
            clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
        
        # Replace separators with spaces and clean up
        clean_name = re.sub(r'[_\-\.]', ' ', clean_name)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        # Capitalize properly
        clean_name = ' '.join(word.capitalize() for word in clean_name.split())
        
        return clean_name if clean_name else 'Unknown Movie'
    
    def group_similar_movies(self, movie_name: str, existing_movies: List[str]) -> str:
        """Group similar movie names together"""
        # Simple similarity check - you can enhance this
        for existing in existing_movies:
            if self.calculate_similarity(movie_name.lower(), existing.lower()) > 0.8:
                return existing
        return movie_name
    
    def calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate simple string similarity"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1, str2).ratio()
