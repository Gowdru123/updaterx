import asyncio
import re
import os
from collections import defaultdict
from telethon import TelegramClient, events
import logging
from datetime import datetime, timedelta
from config import Config
import time
from image_search import image_search

# Try to import replit db, fallback to dict if not available
try:
    from replit import db
    IS_REPLIT = True
except (ImportError, AttributeError):
    # Fallback for non-Replit environments
    db = {}
    IS_REPLIT = False
    print("Running outside Replit environment - using in-memory storage")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration - Add these to your secrets
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_CHANNEL_ID = int(os.getenv('DB_CHANNEL_ID', '0')) if os.getenv('DB_CHANNEL_ID') else None  # Channel where movies are uploaded
UPDATE_CHANNEL_ID = int(os.getenv('UPDATE_CHANNEL_ID', '0')) if os.getenv('UPDATE_CHANNEL_ID') else None  # Channel for updates
BOT_USERNAME = os.getenv('BOT_USERNAME', 'Theater_Print_Movies_Search_bot')

# Check required environment variables
if not all([API_ID, API_HASH, BOT_TOKEN, DB_CHANNEL_ID, UPDATE_CHANNEL_ID]):
    logger.error("Missing required environment variables. Please set API_ID, API_HASH, BOT_TOKEN, DB_CHANNEL_ID, and UPDATE_CHANNEL_ID")
    exit(1)

client = TelegramClient('movie_bot', API_ID, API_HASH)

# Global variables for batching updates
locks = defaultdict(asyncio.Lock)
pending_updates = {}

# Precompiled regex patterns
CLEAN_PATTERN = re.compile(r'@[^ \n\r\t\.,:;!?()\[\]{}<>\\/"\'=_%]+|\bwww\.[^\s\]\)]+|\([\@^]+\)|\[[\@^]+\]')
NORMALIZE_PATTERN = re.compile(r"[._]+|[()\[\]{}:;'–!,.?_]")
QUALITY_PATTERN = re.compile(
    r"\b(?:HDCam|HDTC|CamRip|TS|TC|TeleSync|DVDScr|DVDRip|PreDVD|"
    r"WEBRip|WEB-DL|TVRip|HDTV|WEB DL|WebDl|BluRay|BRRip|BDRip|"
    r"360p|480p|720p|1080p|2160p|4K|1440p|540p|240p|140p|HEVC|HDRip)\b",
    re.IGNORECASE
)
YEAR_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?![A-Za-z0-9])")
RANGE_REGEX = re.compile(r'\bS(\d{1,2})[^\w\n\r]*E(?:p(?:isode)?)?0*(\d{1,2})_to_0*(\d{1,2})',re.IGNORECASE)
SINGLE_REGEX = re.compile(r'\bS(\d{1,2})[^\w\n\r]*E(?:p(?:isode)?)?0*(\d{1,3})', re.IGNORECASE)
NAMED_REGEX = re.compile(r'Season\s*0*(\d{1,2})[\s\-,:]*Ep(?:isode)?\s*0*(\d{1,3})', re.IGNORECASE)
EP_ONLY_RANGE = re.compile(r'\b(?:EP|Episode)0*(\d{1,3})\s*-\s*0*(\d{1,3})\b',re.IGNORECASE)

# Constants
IGNORE_WORDS = {
    "rarbg", "dub", "sub", "sample", "mkv", "aac", "combined",
    "action", "adventure", "animation", "biography", "comedy", "crime",
    "documentary", "drama", "family", "fantasy", "film-noir", "history",
    "horror", "music", "musical", "mystery", "romance", "sci-fi", "sport",
    "thriller", "war", "western", "hdcam", "hdtc", "camrip", "ts", "tc",
    "telesync", "dvdscr", "dvdrip", "predvd", "webrip", "web-dl", "tvrip",
    "hdtv", "web", "dl", "webdl", "bluray", "brrip", "bdrip", "360p", "480p",
    "720p", "1080p", "2160p", "4k", "1440p", "540p", "240p", "140p", "hevc",
    "hdrip", "hin", "hindi", "tam", "tamil", "kan", "kannada", "tel", "telugu",
    "mal", "malayalam", "eng", "english", "pun", "punjabi", "ben", "bengali",
    "mar", "marathi", "guj", "gujarati", "urd", "urdu", "kor", "korean", "jpn",
    "japanese", "nf", "netflix", "sonyliv", "sony", "sliv", "amzn", "prime",
    "primevideo", "hotstar", "zee5", "jio", "jhs", "aha", "hbo", "paramount",
    "apple", "hoichoi", "sunnxt", "viki", "rm_movie_flix", "rm", "movie", "flix",
    "hq", "hdrip", "jnk_backup", "jnk", "backup", "dd", "moviez", "shetty", "moviez2",
    "shettymoviez", "shettymoviez2", "thedd", "snxt", "h", "264", "aac2", "0", "adda", 
    "addafiles", "files", "cinema", "films", "theater", "print", "movies", "we", "ds4k",
    "10bit", "bit", "x264", "x265", "cam", "esub", "msub", "org", "original", "dual",
    "multi", "dubbed", "subtitled", "uhd", "fhd", "hd", "quality", "rip", "cam", "tc",
    "~", "-", "_", ".", "(", ")", "[", "]", "{", "}", ""}

CAPTION_LANGUAGES = {
    "hin": "Hindi", "hindi": "Hindi",
    "tam": "Tamil", "tamil": "Tamil",
    "kan": "Kannada", "kannada": "Kannada",
    "tel": "Telugu", "telugu": "Telugu",
    "mal": "Malayalam", "malayalam": "Malayalam",
    "eng": "English", "english": "English",
    "pun": "Punjabi", "punjabi": "Punjabi",
    "ben": "Bengali", "bengali": "Bengali",
    "mar": "Marathi", "marathi": "Marathi",
    "guj": "Gujarati", "gujarati": "Gujarati",
    "urd": "Urdu", "urdu": "Urdu",
    "kor": "Korean", "korean": "Korean",
    "jpn": "Japanese", "japanese": "Japanese",
}

class MovieProcessor:
    def __init__(self):
        self.movie_data = defaultdict(lambda: {
            'files': [],
            'qualities': set(),
            'languages': set(),
            'message_id': None,
            'is_photo': False,
            'tag': '#MOVIE',
            'episodes_by_season': defaultdict(set)
        })

    def clean_mentions_links(self, text):
        return CLEAN_PATTERN.sub("", text or "").strip()

    def normalize(self, s):
        s = NORMALIZE_PATTERN.sub(" ", s)
        return re.sub(r"\s+", " ", s).strip()

    def remove_ignored_words(self, text):
        IGNORE_WORDS_LOWER = {w.lower() for w in IGNORE_WORDS}
        return " ".join(word for word in text.split() if word.lower() not in IGNORE_WORDS_LOWER)

    def extract_clean_movie_name_with_year_cutoff(self, filename):
        """Extract movie name stopping at year (ignores everything after year)"""
        logger.info(f"🔍 Starting year-cutoff movie name extraction for: {filename}")

        # Step 1: Remove file extension first
        name_without_ext = re.sub(r'\.[^.]+$', '', filename)
        logger.info(f"📝 After removing extension: {name_without_ext}")

        # Step 2: Find year in the filename
        year_match = YEAR_PATTERN.search(name_without_ext)
        if not year_match:
            logger.info(f"📅 No year found, falling back to standard extraction")
            return self.extract_clean_movie_name_standard(filename)

        year_position = year_match.start()
        name_before_year = name_without_ext[:year_position].strip()
        logger.info(f"📅 Found year '{year_match.group()}' at position {year_position}")
        logger.info(f"🔪 Text before year: '{name_before_year}'")

        if not name_before_year:
            logger.warning(f"⚠️ No text before year, falling back to standard extraction")
            return self.extract_clean_movie_name_standard(filename)

        # Step 3: Split text before year into tokens
        tokens = re.split(r'[\s\-_\.~]+', name_before_year)
        tokens = [token for token in tokens if token]  # Remove empty tokens
        logger.info(f"🔤 Tokens before year: {tokens}")

        # Step 4: Clean tokens (remove channel names and bad words)
        clean_tokens = []
        ignore_words_lower = {word.lower() for word in IGNORE_WORDS}
        
        # Channel name patterns to ignore
        channel_patterns = [
            r'^@.*',  # Any token starting with @
            r'.*moviez.*', r'.*flix.*', r'.*cinema.*', r'.*films.*',
            r'shetty.*', r'.*backup.*', r'.*files.*', r'.*adda.*',
            r'rm_.*', r'.*_rm', r'jnk.*', r'.*dd.*moviez.*',
            r'the.*dd.*', r'.*print.*', r'.*theater.*'
        ]

        for i, token in enumerate(tokens):
            logger.info(f"🔍 Processing token {i+1}: '{token}'")

            # Remove special characters from token for checking
            token_cleaned = re.sub(r'[@#~\-_()]+', '', token)
            token_lower = token_cleaned.lower()

            # Skip empty tokens after cleaning
            if not token_cleaned:
                logger.info(f"❌ Token became empty after cleaning, skipping")
                continue

            # Check if token matches channel name patterns
            is_channel_name = False
            for pattern in channel_patterns:
                if re.match(pattern, token_lower):
                    logger.info(f"❌ Token '{token}' matches channel pattern '{pattern}', removing")
                    is_channel_name = True
                    break
            
            if is_channel_name:
                continue

            # Check exact match with ignore words (case insensitive)
            if token_lower in ignore_words_lower:
                logger.info(f"❌ Token '{token_cleaned}' found in ignore list, removing")
                continue

            # Check if token contains common bad word patterns
            bad_patterns = ['moviez', 'flix', 'shetty', 'backup', 'files', 'adda', 'print']
            contains_bad_pattern = any(bad in token_lower for bad in bad_patterns)
            if contains_bad_pattern:
                logger.info(f"❌ Token '{token_cleaned}' contains bad pattern, removing")
                continue

            # Token passed all checks, add to clean list
            if len(token_cleaned) >= 2:  # Require at least 2 characters for meaningful tokens
                clean_tokens.append(token_cleaned)
                logger.info(f"✅ Token '{token_cleaned}' added to clean list")
            elif len(token_cleaned) == 1 and token_cleaned.isalpha():
                # Allow single letter only if it's alphabetic (like "V" in "Gen V")
                clean_tokens.append(token_cleaned)
                logger.info(f"✅ Single letter token '{token_cleaned}' added to clean list")
            else:
                logger.info(f"❌ Token '{token_cleaned}' too short or invalid, skipping")

        # Step 5: Join clean tokens
        if clean_tokens:
            movie_name = ' '.join(clean_tokens)
            logger.info(f"🎬 Joined clean tokens: '{movie_name}'")

            # Final cleanup - normalize spaces
            movie_name = re.sub(r'\s+', ' ', movie_name).strip()

            # Capitalize properly
            movie_name = ' '.join(word.capitalize() for word in movie_name.split())
            logger.info(f"✨ Final movie name (year-cutoff method): '{movie_name}'")

            return movie_name
        else:
            logger.warning(f"⚠️ No valid tokens found before year, falling back to standard extraction")
            return self.extract_clean_movie_name_standard(filename)

    def extract_clean_movie_name_standard(self, filename):
        """Standard movie name extraction method (original logic)"""
        logger.info(f"🔍 Starting standard movie name extraction for: {filename}")

        # Step 1: Remove file extension first
        name_without_ext = re.sub(r'\.[^.]+$', '', filename)
        logger.info(f"📝 After removing extension: {name_without_ext}")

        # Step 2: Split into tokens using multiple delimiters
        tokens = re.split(r'[\s\-_\.~]+', name_without_ext)
        tokens = [token for token in tokens if token]  # Remove empty tokens
        logger.info(f"🔤 Tokens after splitting: {tokens}")

        # Step 3: Enhanced filtering - remove channel names and bad words
        clean_tokens = []
        ignore_words_lower = {word.lower() for word in IGNORE_WORDS}
        
        # Add more channel name patterns to ignore
        channel_patterns = [
            r'^@.*',  # Any token starting with @
            r'.*moviez.*', r'.*flix.*', r'.*cinema.*', r'.*films.*',
            r'shetty.*', r'.*backup.*', r'.*files.*', r'.*adda.*',
            r'rm_.*', r'.*_rm', r'jnk.*', r'.*dd.*moviez.*',
            r'the.*dd.*', r'.*print.*', r'.*theater.*'
        ]

        for i, token in enumerate(tokens):
            logger.info(f"🔍 Processing token {i+1}: '{token}'")

            # Remove special characters from token for checking
            token_cleaned = re.sub(r'[@#~\-_()]+', '', token)
            token_lower = token_cleaned.lower()

            # Skip empty tokens after cleaning
            if not token_cleaned:
                logger.info(f"❌ Token became empty after cleaning, skipping")
                continue

            # Check if token matches channel name patterns
            is_channel_name = False
            for pattern in channel_patterns:
                if re.match(pattern, token_lower):
                    logger.info(f"❌ Token '{token}' matches channel pattern '{pattern}', removing")
                    is_channel_name = True
                    break
            
            if is_channel_name:
                continue

            # Check exact match with ignore words (case insensitive)
            if token_lower in ignore_words_lower:
                logger.info(f"❌ Token '{token_cleaned}' found in ignore list, removing")
                continue

            # Check if token contains common bad word patterns
            bad_patterns = ['moviez', 'flix', 'shetty', 'backup', 'files', 'adda', 'print']
            contains_bad_pattern = any(bad in token_lower for bad in bad_patterns)
            if contains_bad_pattern:
                logger.info(f"❌ Token '{token_cleaned}' contains bad pattern, removing")
                continue

            # Check if token is a year (stop processing after year)
            if YEAR_PATTERN.match(token_cleaned):
                logger.info(f"📅 Found year '{token_cleaned}', stopping processing")
                break

            # Check if token starts with bracket and year
            if re.match(r'^\(\d{4}\)', token_cleaned):
                logger.info(f"📅 Found bracketed year '{token_cleaned}', stopping processing")
                break

            # Check if token is quality indicator
            if QUALITY_PATTERN.search(token_cleaned):
                logger.info(f"🎯 Found quality indicator '{token_cleaned}', stopping processing")
                break

            # Check if token is language indicator
            if token_lower in CAPTION_LANGUAGES:
                logger.info(f"🌍 Found language indicator '{token_cleaned}', stopping processing")
                break

            # Check for series indicators
            if re.match(r'^(s\d{1,2}|season|episode|ep|part)$', token_lower):
                logger.info(f"📺 Found series indicator '{token_cleaned}', stopping processing")
                break

            # Check for file size indicators
            if re.match(r'^\d+(\.\d+)?(gb|mb)$', token_lower):
                logger.info(f"📊 Found file size '{token_cleaned}', stopping processing")
                break

            # Check for technical terms
            tech_terms = ['ds4k', '10bit', 'hevc', 'x264', 'x265', 'aac', 'ac3', 'dts', 'webrip', 'web-dl']
            if token_lower in tech_terms:
                logger.info(f"🔧 Found technical term '{token_cleaned}', stopping processing")
                break

            # Token passed all checks, add to clean list
            if len(token_cleaned) >= 2:  # Require at least 2 characters for meaningful tokens
                clean_tokens.append(token_cleaned)
                logger.info(f"✅ Token '{token_cleaned}' added to clean list")
            elif len(token_cleaned) == 1 and token_cleaned.isalpha():
                # Allow single letter only if it's alphabetic (like "V" in "Gen V")
                clean_tokens.append(token_cleaned)
                logger.info(f"✅ Single letter token '{token_cleaned}' added to clean list")
            else:
                logger.info(f"❌ Token '{token_cleaned}' too short or invalid, skipping")

        # Step 4: Join clean tokens
        if clean_tokens:
            movie_name = ' '.join(clean_tokens)
            logger.info(f"🎬 Joined clean tokens: '{movie_name}'")

            # Final cleanup - normalize spaces
            movie_name = re.sub(r'\s+', ' ', movie_name).strip()

            # Capitalize properly
            movie_name = ' '.join(word.capitalize() for word in movie_name.split())
            logger.info(f"✨ Final movie name: '{movie_name}'")

            return movie_name
        else:
            logger.warning(f"⚠️ No valid tokens found, returning 'Unknown Movie'")
            return "Unknown Movie"

    def extract_clean_movie_name(self, filename):
        """Main movie name extraction method - tries year-cutoff first, then standard"""
        # First try the year-cutoff method
        return self.extract_clean_movie_name_with_year_cutoff(filename)

    def get_qualities(self, text):
        qualities = QUALITY_PATTERN.findall(text)
        return ", ".join(qualities) if qualities else "N/A"

    def extract_season_episode(self, filename):
        if m := EP_ONLY_RANGE.search(filename):
            return 1, f"{int(m.group(1))}-{int(m.group(2))}"
        for pattern in (RANGE_REGEX, SINGLE_REGEX, NAMED_REGEX):
            if m := pattern.search(filename):
                season = int(m.group(1))
                if pattern == RANGE_REGEX:
                    ep = f"{m.group(2)}-{m.group(3)}"
                else:
                    ep = m.group(2)
                return season, ep
        return None, None

    def extract_quality_from_tokens(self, filename):
        """Extract quality using token-based method similar to movie name extraction"""
        logger.info(f"🎯 Extracting quality from: {filename}")

        # Split into tokens using multiple delimiters
        tokens = re.split(r'[\s\-_\.]+', filename)
        quality_tokens = []

        # Quality indicators to look for (more comprehensive)
        quality_patterns = {
            'hdcam': 'HDCAM', 'hdtc': 'HDTC', 'camrip': 'CAMRip', 'cam': 'CAM',
            'ts': 'TS', 'tc': 'TC', 'telesync': 'TeleSync',
            'dvdscr': 'DVDScr', 'dvdrip': 'DVDRip', 'predvd': 'PreDVD',
            'webrip': 'WEBRip', 'web-dl': 'WEB-DL', 'webdl': 'WEBRip', 'web': 'WEB',
            'tvrip': 'TVRip', 'hdtv': 'HDTV', 'bluray': 'BluRay', 'brrip': 'BRRip',
            'bdrip': 'BDRip', 'hevc': 'HEVC', 'hdrip': 'HDRip',
            '360p': '360p', '480p': '480p', '720p': '720p', '1080p': '1080p',
            '2160p': '2160p', '4k': '4K', '1440p': '1440p', '540p': '540p',
            '240p': '240p', '140p': '140p', 'uhd': 'UHD', 'fhd': 'FHD', 'hd': 'HD'
        }

        for token in tokens:
            # Clean token but preserve original case for display
            token_clean = re.sub(r'[@#~\-_()]+', '', token).lower()
            if token_clean in quality_patterns:
                quality_tokens.append(quality_patterns[token_clean])
                logger.info(f"✅ Found quality token: {token_clean} -> {quality_patterns[token_clean]}")

        # Also check for resolution patterns that might be written differently
        resolution_pattern = re.search(r'\b(\d{3,4})p?\b', filename, re.IGNORECASE)
        if resolution_pattern:
            res_value = resolution_pattern.group(1)
            if res_value in ['360', '480', '720', '1080', '2160']:
                res_quality = f"{res_value}p"
                if res_quality not in quality_tokens:
                    quality_tokens.append(res_quality)
                    logger.info(f"✅ Found resolution pattern: {res_quality}")

        # Remove duplicates while preserving order
        unique_qualities = []
        for quality in quality_tokens:
            if quality not in unique_qualities:
                unique_qualities.append(quality)

        result = ", ".join(unique_qualities) if unique_qualities else "N/A"
        logger.info(f"🎯 Final quality: {result}")
        return result

    def format_file_size(self, size_in_bytes):
        """Formats file size in a human-readable way (e.g., 1.2GB, 250MB)"""
        if size_in_bytes is None:
            return "N/A"

        if size_in_bytes < 1024:
            return f"{size_in_bytes} B"
        elif size_in_bytes < 1024**2:
            return f"{size_in_bytes / 1024:.2f} KB"
        elif size_in_bytes < 1024**3:
            return f"{size_in_bytes / (1024**2):.2f} MB"
        else:
            return f"{size_in_bytes / (1024**3):.2f} GB"

    def extract_language_from_tokens(self, filename):
        """Extract language using token-based method similar to movie name extraction"""
        logger.info(f"🌍 Extracting language from: {filename}")

        # First check for bracket format like [Tam + Tel + Hin + Mal + Kan + Eng]
        bracket_pattern = re.search(r'\[([^\]]+)\]', filename)
        if bracket_pattern:
            bracket_content = bracket_pattern.group(1)
            logger.info(f"🔍 Found bracket content: {bracket_content}")

            # Split by + and clean each language
            bracket_langs = re.split(r'\s*\+\s*', bracket_content)
            language_tokens = []

            for lang in bracket_langs:
                lang_clean = lang.strip().lower()
                # Map common abbreviations to full names
                lang_mapping = {
                    'tam': 'Tamil', 'tel': 'Telugu', 'hin': 'Hindi',
                    'mal': 'Malayalam', 'kan': 'Kannada', 'eng': 'English',
                    'ben': 'Bengali', 'mar': 'Marathi', 'guj': 'Gujarati',
                    'pun': 'Punjabi', 'urd': 'Urdu', 'kor': 'Korean', 'jpn': 'Japanese'
                }

                if lang_clean in lang_mapping:
                    language_tokens.append(lang_mapping[lang_clean])
                    logger.info(f"✅ Found bracket language: {lang_clean} -> {lang_mapping[lang_clean]}")
                elif lang_clean in CAPTION_LANGUAGES:
                    language_tokens.append(CAPTION_LANGUAGES[lang_clean])
                    logger.info(f"✅ Found bracket language: {lang_clean} -> {CAPTION_LANGUAGES[lang_clean]}")

            if language_tokens:
                result = ", ".join(language_tokens)
                logger.info(f"🌍 Final language from brackets: {result}")
                return result

        # Token-based method - split filename into tokens
        tokens = re.split(r'[\s\-_\.]+', filename)
        language_tokens = []

        # Extended language patterns including exact matches
        extended_languages = {
            # Direct language names
            'hindi': 'Hindi', 'english': 'English', 'tamil': 'Tamil', 
            'telugu': 'Telugu', 'malayalam': 'Malayalam', 'kannada': 'Kannada',
            'bengali': 'Bengali', 'marathi': 'Marathi', 'gujarati': 'Gujarati',
            'punjabi': 'Punjabi', 'urdu': 'Urdu', 'korean': 'Korean', 'japanese': 'Japanese',
            # Abbreviations
            'hin': 'Hindi', 'eng': 'English', 'tam': 'Tamil', 'tel': 'Telugu',
            'mal': 'Malayalam', 'kan': 'Kannada', 'ben': 'Bengali', 'mar': 'Marathi',
            'guj': 'Gujarati', 'pun': 'Punjabi', 'urd': 'Urdu', 'kor': 'Korean', 'jpn': 'Japanese',
            # Additional patterns
            'dual': 'Dual Audio', 'multi': 'Multi Audio', 'dubbed': 'Dubbed',
            'org': 'Original', 'original': 'Original', 'sub': 'Subtitled',
            'esub': 'English Sub', 'msub': 'Multi Sub'
        }

        for token in tokens:
            # Clean token but preserve original case for checking
            original_token = token.lower()
            token_clean = re.sub(r'[@#~\-_()]+', '', original_token)

            # Check both cleaned and original token
            for check_token in [token_clean, original_token]:
                if check_token in extended_languages:
                    language_name = extended_languages[check_token]
                    if language_name not in language_tokens:
                        language_tokens.append(language_name)
                        logger.info(f"✅ Found language token: {check_token} -> {language_name}")

        result = ", ".join(language_tokens) if language_tokens else "N/A"
        logger.info(f"🌍 Final language: {result}")
        return result

    def extract_language_from_caption(self, caption_text):
        """Extract language from message caption (hashtags and text patterns)"""
        if not caption_text:
            return "N/A"

        logger.info(f"🌍 Extracting language from caption: {caption_text}")

        # Look for hashtag patterns like #Hindi, #Tamil etc.
        hashtag_pattern = re.findall(r'#(\w+)', caption_text)
        language_tokens = []

        # Language mapping for hashtags and text
        lang_mapping = {
            'hindi': 'Hindi', 'english': 'English', 'tamil': 'Tamil', 
            'telugu': 'Telugu', 'malayalam': 'Malayalam', 'kannada': 'Kannada',
            'bengali': 'Bengali', 'marathi': 'Marathi', 'gujarati': 'Gujarati',
            'punjabi': 'Punjabi', 'urdu': 'Urdu', 'korean': 'Korean', 'japanese': 'Japanese'
        }

        # Check hashtags
        for hashtag in hashtag_pattern:
            hashtag_lower = hashtag.lower()
            if hashtag_lower in lang_mapping:
                language_name = lang_mapping[hashtag_lower]
                if language_name not in language_tokens:
                    language_tokens.append(language_name)
                    logger.info(f"✅ Found caption language: #{hashtag} -> {language_name}")

        # Also check for direct language mentions in caption text
        caption_lower = caption_text.lower()
        for lang_key, lang_name in lang_mapping.items():
            if lang_key in caption_lower and lang_name not in language_tokens:
                language_tokens.append(lang_name)
                logger.info(f"✅ Found caption text language: {lang_key} -> {lang_name}")

        # Check for common patterns like "Tamil", "Hindi" etc.
        text_pattern = re.findall(r'\b(Tamil|Hindi|English|Telugu|Malayalam|Kannada|Bengali|Marathi|Gujarati|Punjabi|Urdu|Korean|Japanese)\b', caption_text, re.IGNORECASE)
        for lang in text_pattern:
            lang_name = lang.capitalize()
            if lang_name not in language_tokens:
                language_tokens.append(lang_name)
                logger.info(f"✅ Found direct language mention: {lang} -> {lang_name}")

        result = ", ".join(language_tokens) if language_tokens else "N/A"
        logger.info(f"🌍 Final caption language: {result}")
        return result

    def extract_media_info(self, filename, file_size_bytes, caption_text=None):
        # Use the new enhanced movie name extraction
        base_name = self.extract_clean_movie_name(filename)

        # Extract year from original filename
        year = None
        if year_match := YEAR_PATTERN.search(filename):
            year = year_match.group(0)

        # Get quality and file size using token-based method
        quality = self.extract_quality_from_tokens(filename)

        # Get language from both filename and caption, prioritize caption
        language_from_filename = self.extract_language_from_tokens(filename)
        language_from_caption = self.extract_language_from_caption(caption_text)

        # Combine languages, prioritizing caption
        all_languages = []
        if language_from_caption != "N/A":
            all_languages.extend(language_from_caption.split(", "))
        if language_from_filename != "N/A":
            filename_langs = language_from_filename.split(", ")
            for lang in filename_langs:
                if lang not in all_languages:
                    all_languages.append(lang)

        language = ", ".join(all_languages) if all_languages else "N/A"

        # Use actual file size from document
        file_size = self.format_file_size(file_size_bytes) if file_size_bytes else "N/A"

        # Check for TV series episodes
        season, episode = self.extract_season_episode(filename)
        tag = "#SERIES" if season is not None else "#MOVIE"

        # For series, create a series base name without episode info
        if tag == "#SERIES":
            # Remove episode info from base name
            series_base = re.sub(r'\s*S\d{1,2}E\d{1,3}.*$', '', base_name, flags=re.IGNORECASE)
            series_base = re.sub(r'\s*Season\s*\d+.*$', '', series_base, flags=re.IGNORECASE)
            series_base = re.sub(r'\s*Episode\s*\d+.*$', '', series_base, flags=re.IGNORECASE)
            if year and year in series_base:
                series_base = series_base.replace(year, "").strip()
            base_name = series_base.strip()

        return {
            "processed": filename,
            "base_name": base_name,
            "tag": tag,
            "season": season,
            "episode": episode,
            "year": year,
            "quality": quality,
            "language": language,
            "file_size": file_size
        }

    def generate_download_link(self, movie_name):
        """Generate download link for the movie"""
        clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', movie_name)
        clean_name = re.sub(r'\s+', '-', clean_name.strip())
        words = clean_name.split('-')[:2]
        simple_name = '-'.join(words) if words else 'Movie'
        return f"https://t.me/{BOT_USERNAME}?start=getfile-{simple_name}"

    def generate_search_link(self, movie_name):
        """Generate search link that auto-fills movie name in bot"""
        # Clean movie name for URL - remove special characters, keep spaces as dashes
        clean_name = re.sub(r'[^\w\s-]', '', movie_name)
        clean_name = re.sub(r'\s+', '-', clean_name.strip())
        return f"https://t.me/{BOT_USERNAME}?start=getfile-{clean_name}"

    def format_movie_message(self, movie_name, data):
        """Format the movie information message using configurable templates"""
        from config import Config

        all_qualities = set()
        all_languages = set()
        all_years = set()
        all_file_sizes = []
        episodes_by_season = defaultdict(set)

        # Process all files to collect complete information
        for file in data['files']:
            if file.get("quality") and file["quality"] != "N/A":
                all_qualities.update(q.strip() for q in file["quality"].split(",") if q.strip())
            if file.get("language") and file["language"] != "N/A":
                all_languages.update(l.strip() for l in file["language"].split(",") if l.strip())
            if file.get("year"):
                all_years.add(file["year"])
            if file.get("file_size") and file["file_size"] != "N/A":
                all_file_sizes.append(file["file_size"])
            if file.get("season") and file.get("episode"):
                season = file["season"]
                episode = file["episode"]
                episodes_by_season[season].add(episode)

        file_count = len(data['files'])
        primary_tag = data.get('tag', '#MOVIE')

        # Prepare template variables
        year_str = sorted(all_years)[0] if all_years else "N/A"
        quality_str = ", ".join(sorted(all_qualities)) if all_qualities else "N/A"
        language_str = ", ".join(sorted(all_languages)) if all_languages else "N/A"
        file_sizes_str = " | ".join(all_file_sizes) if all_file_sizes else "N/A"

        # Generate search link
        search_link = self.generate_search_link(movie_name)

        if primary_tag == "#SERIES" and episodes_by_season:
            # Format episodes for series
            episode_lines = []
            for season, episodes in sorted(episodes_by_season.items(), key=lambda x: int(x[0])):
                singles = []
                ranges = []

                for ep in episodes:
                    if "-" in ep:
                        ranges.append(ep)
                    else:
                        try:
                            singles.append(int(ep))
                        except ValueError:
                            ranges.append(ep)

                singles.sort()
                collapsed = []
                start = end = None
                for num in singles:
                    if start is None:
                        start = end = num
                    elif num == end + 1:
                        end = num
                    else:
                        collapsed.append(str(start) if start == end else f"{start}-{end}")
                        start = end = num
                if start is not None:
                    collapsed.append(str(start) if start == end else f"{start}-{end}")

                all_ep_parts = collapsed + sorted(ranges, key=lambda s: int(s.split("-")[0]))
                episode_lines.append(f"<b>S{int(season)}:</b> {', '.join(all_ep_parts)}")

            episodes_str = "\n".join(episode_lines)

            # Use series template 
            message = Config.SERIES_TEMPLATE.format(
                title=movie_name,
                quality=quality_str,
                language=language_str,
                year=year_str,
                file_sizes=file_sizes_str,
                episodes=episodes_str,
                total_files=file_count
            )
        else:
            # Use movie template
            message = Config.MOVIE_TEMPLATE.format(
                title=movie_name,
                quality=quality_str,
                language=language_str,
                year=year_str,
                file_sizes=file_sizes_str,
                total_files=file_count
            )

        return message

processor = MovieProcessor()

async def cleanup_old_files():
    """Delete movie files and posts older than 24 hours (real time, not bot uptime)"""
    try:
        logger.info("🧹 Starting cleanup of files older than 24 hours (real time)")
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(hours=24)
        logger.info(f"🕒 Current time: {current_time}")
        logger.info(f"⏰ Cutoff time: {cutoff_time}")

        movies_to_delete = []
        for movie_name, movie_data in processor.movie_data.items():
            # Check if ALL files are older than 24 hours (real time)
            should_delete = True
            oldest_file_time = None
            newest_file_time = None
            
            for file_info in movie_data['files']:
                try:
                    file_timestamp = datetime.fromisoformat(file_info['timestamp'])
                    if oldest_file_time is None or file_timestamp < oldest_file_time:
                        oldest_file_time = file_timestamp
                    if newest_file_time is None or file_timestamp > newest_file_time:
                        newest_file_time = file_timestamp
                    
                    # If ANY file is newer than cutoff, keep the movie
                    if file_timestamp >= cutoff_time:
                        should_delete = False
                        break
                except (ValueError, KeyError) as e:
                    logger.warning(f"⚠️ Invalid timestamp for file in {movie_name}: {e}")
                    continue
            
            if should_delete and oldest_file_time:
                age_hours = (current_time - oldest_file_time).total_seconds() / 3600
                logger.info(f"🗑️ Movie '{movie_name}' marked for deletion - oldest file is {age_hours:.1f} hours old")
                movies_to_delete.append(movie_name)
            elif newest_file_time:
                age_hours = (current_time - newest_file_time).total_seconds() / 3600
                logger.info(f"✅ Movie '{movie_name}' kept - newest file is {age_hours:.1f} hours old")

        # Delete old movies
        for movie_name in movies_to_delete:
            try:
                movie_data = processor.movie_data[movie_name]

                # Delete the update channel post
                if movie_data.get('message_id'):
                    try:
                        await client.delete_messages(UPDATE_CHANNEL_ID, movie_data['message_id'])
                        logger.info(f"🗑️ Deleted update post for: {movie_name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete update post for {movie_name}: {e}")

                # Delete from database
                db_key = f"movie_{movie_name}"
                if db_key in db:
                    if IS_REPLIT:
                        del db[db_key]
                    else:
                        db.pop(db_key, None)
                    logger.info(f"🗑️ Deleted from database: {movie_name}")

                # Delete from memory
                del processor.movie_data[movie_name]
                logger.info(f"🗑️ Cleaned up old movie: {movie_name}")

            except Exception as e:
                logger.error(f"Error deleting movie {movie_name}: {e}")

        if movies_to_delete:
            logger.info(f"🧹 Cleanup completed. Deleted {len(movies_to_delete)} old movies")
        else:
            logger.info("🧹 No old movies to clean up")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def schedule_cleanup():
    """Schedule periodic cleanup every hour (persistent across restarts)"""
    loop = asyncio.get_event_loop()
    
    # Run cleanup immediately on startup to catch files that expired while bot was offline
    loop.create_task(cleanup_old_files())
    
    # Schedule next cleanup in 1 hour
    loop.call_later(3600, lambda: asyncio.create_task(cleanup_old_files()))
    loop.call_later(3600, schedule_cleanup)  # Schedule next cleanup

def schedule_update(movie_name, delay=5):
    """Schedule a delayed update to batch multiple files together"""
    if handle := pending_updates.get(movie_name):
        if not handle.cancelled():
            handle.cancel()

    loop = asyncio.get_event_loop()
    pending_updates[movie_name] = loop.call_later(
        delay,
        lambda: asyncio.create_task(update_movie_post(movie_name))
    )

@client.on(events.NewMessage(pattern='/start'))
async def handle_start_command(event):
    """Handle /start command with getfile parameter"""
    try:
        command = event.message.text
        if command and 'getfile-' in command:
            # Extract movie name from command
            movie_param = command.split('getfile-', 1)[1]
            movie_name = movie_param.replace('-', ' ')

            # Send the movie name as a message that user can copy
            response_message = f"🎬 **Movie Search:**\n\n`{movie_name}`\n\n📋 **Tap to copy the movie name above and send it to search for files!**"

            await event.reply(response_message, parse_mode='markdown')
            logger.info(f"Sent movie name for copying: {movie_name}")
    except Exception as e:
        logger.error(f"Error handling start command: {e}")

def is_video_file(self, filename):
        """Check if file is a video file based on extension"""
        if not filename:
            return False
        
        video_extensions = [
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
            '.m4v', '.3gp', '.f4v', '.asf', '.rm', '.rmvb', '.vob',
            '.ogv', '.drc', '.mng', '.qt', '.yuv', '.m2v', '.m4p',
            '.m4r', '.mpg', '.mp2', '.mpeg', '.mpe', '.mpv', '.m2p',
            '.svi', '.3g2', '.mxf', '.roq', '.nsv'
        ]
        
        file_ext = '.' + filename.lower().split('.')[-1] if '.' in filename else ''
        is_video = file_ext in video_extensions
        
        logger.info(f"🎬 File '{filename}' extension '{file_ext}' - Video: {is_video}")
        return is_video

@client.on(events.NewMessage(chats=DB_CHANNEL_ID))
async def handle_new_file(event):
    """Handle new files uploaded to DB channel"""
    try:
        logger.info(f"🆕 New message received in DB channel")

        if not event.message.document:
            logger.info(f"📄 Message has no document, skipping")
            return

        filename = event.message.document.attributes[0].file_name if event.message.document.attributes else "Unknown"
        file_size_bytes = event.message.document.size
        caption_text = event.message.text or ""
        logger.info(f"📁 Processing file: {filename}")
        if caption_text:
            logger.info(f"📝 Caption text: {caption_text[:100]}...")

        # Check if it's a video file - now accepts all video types
        if not processor.is_video_file(filename):
            logger.info(f"🚫 File '{filename}' is not a video file, skipping")
            return

        # Extract movie information using the improved method
        logger.info(f"🔄 Starting media info extraction...")
        media_info = processor.extract_media_info(filename, file_size_bytes, caption_text)
        movie_name = media_info['base_name']
        logger.info(f"🎬 Extracted movie name: '{movie_name}'")
        logger.info(f"📊 Media info: Quality={media_info['quality']}, Language={media_info['language']}, Tag={media_info['tag']}, File Size={media_info['file_size']}")

        if not movie_name or len(movie_name) < 2:
            logger.warning(f"❌ Could not extract valid movie name from: {filename}")
            return

        # Use async lock for thread safety
        lock = locks[movie_name]
        logger.info(f"🔒 Acquiring lock for movie: {movie_name}")
        async with lock:
            logger.info(f"✅ Lock acquired for movie: {movie_name}")

            # Create unique identifier using filename + file size for better duplicate detection
            file_identifier = f"{filename}_{file_size_bytes}"
            existing_identifiers = [f"{f['filename']}_{f.get('file_size_bytes', 0)}" for f in processor.movie_data[movie_name]['files']]
            if file_identifier in existing_identifiers:
                logger.info(f"⚠️ File with same name and size already exists: {filename}")
                return

            # Also check by file_id to prevent exact duplicates
            existing_file_ids = [f['file_id'] for f in processor.movie_data[movie_name]['files']]
            if event.message.document.id in existing_file_ids:
                logger.info(f"⚠️ File with same file_id already exists: {event.message.document.id}")
                return

            logger.info(f"📝 Creating file data entry for: {filename}")
            # Create file data
            file_data = {
                'filename': filename,
                'processed': media_info['processed'],
                'message_id': event.message.id,
                'file_id': event.message.document.id,
                'file_size_bytes': file_size_bytes,
                'timestamp': datetime.now().isoformat(),
                'quality': media_info['quality'],
                'language': media_info['language'],
                'year': media_info['year'],
                'season': media_info['season'],
                'episode': media_info['episode'],
                'file_size': media_info['file_size']
            }

            # Update movie data
            processor.movie_data[movie_name]['files'].append(file_data)
            logger.info(f"📂 Added file to movie data. Total files for '{movie_name}': {len(processor.movie_data[movie_name]['files'])}")

            if media_info['quality'] != "N/A":
                processor.movie_data[movie_name]['qualities'].update(q.strip() for q in media_info['quality'].split(","))
                logger.info(f"🎯 Updated qualities for '{movie_name}': {list(processor.movie_data[movie_name]['qualities'])}")
            if media_info['language'] != "N/A":
                processor.movie_data[movie_name]['languages'].update(l.strip() for l in media_info['language'].split(","))
                logger.info(f"🌍 Updated languages for '{movie_name}': {list(processor.movie_data[movie_name]['languages'])}")

            processor.movie_data[movie_name]['tag'] = media_info['tag']
            logger.info(f"🏷️ Set tag for '{movie_name}': {media_info['tag']}")

            # Handle episodes for series
            if media_info['season'] and media_info['episode']:
                processor.movie_data[movie_name]['episodes_by_season'][media_info['season']].add(media_info['episode'])
                logger.info(f"📺 Added episode S{media_info['season']}E{media_info['episode']} for '{movie_name}'")

            # Store in database for persistence - convert to serializable format
            try:
                logger.info(f"💾 Saving movie data to database for: {movie_name}")
                movie_data_for_db = {
                    'files': processor.movie_data[movie_name]['files'],
                    'qualities': list(processor.movie_data[movie_name]['qualities']),
                    'languages': list(processor.movie_data[movie_name]['languages']),
                    'message_id': processor.movie_data[movie_name]['message_id'],
                    'is_photo': processor.movie_data[movie_name]['is_photo'],
                    'tag': processor.movie_data[movie_name]['tag'],
                    'episodes_by_season': {k: list(v) for k, v in processor.movie_data[movie_name]['episodes_by_season'].items()}
                }
                if IS_REPLIT:
                    db[f"movie_{movie_name}"] = movie_data_for_db
                else:
                    # In non-Replit environments, just store in memory
                    db[f"movie_{movie_name}"] = movie_data_for_db
                logger.info(f"✅ Successfully saved to database: movie_{movie_name}")
            except Exception as e:
                logger.error(f"❌ Error saving to database: {e}")

            logger.info(f"✅ Successfully processed file: {filename} for movie: {movie_name}")

            # Schedule update with delay to batch multiple files
            logger.info(f"⏰ Scheduling update for '{movie_name}' with 5 second delay")
            schedule_update(movie_name, delay=5)

    except Exception as e:
        logger.error(f"Error processing file: {e}")

async def update_movie_post(movie_name):
    """Update or create movie post in update channel (called after delay)"""
    try:
        # Remove from pending updates
        if movie_name in pending_updates:
            del pending_updates[movie_name]

        movie_data = processor.movie_data[movie_name]
        message_text = processor.format_movie_message(movie_name, movie_data)

        # Generate direct download link for text format
        search_link = processor.generate_search_link(movie_name)
        
        # Add download link to message text
        message_text += f"\n\n📥 **ᴅᴏᴡɴʟᴏᴀᴅ ʜᴇʀᴇ:** {search_link}"
        
        buttons = None

        if movie_data['message_id']:
            # Edit existing message
            try:
                await client.edit_message(
                    UPDATE_CHANNEL_ID,
                    movie_data['message_id'],
                    message_text,
                    parse_mode='html',
                    link_preview=False
                )
                logger.info(f"Updated existing post for: {movie_name}")
            except Exception as e:
                logger.warning(f"Failed to edit message, sending new one: {e}")
                # If edit fails, send new message
                sent_message = await client.send_message(
                    UPDATE_CHANNEL_ID,
                    message_text,
                    parse_mode='html',
                    link_preview=False
                )
                processor.movie_data[movie_name]['message_id'] = sent_message.id
                # Update database
                try:
                    movie_data_for_db = {
                        'files': processor.movie_data[movie_name]['files'],
                        'qualities': list(processor.movie_data[movie_name]['qualities']),
                        'languages': list(processor.movie_data[movie_name]['languages']),
                        'message_id': processor.movie_data[movie_name]['message_id'],
                        'is_photo': processor.movie_data[movie_name]['is_photo'],
                        'tag': processor.movie_data[movie_name]['tag'],
                        'episodes_by_season': {k: list(v) for k, v in processor.movie_data[movie_name]['episodes_by_season'].items()}
                    }
                    if IS_REPLIT:
                        db[f"movie_{movie_name}"] = movie_data_for_db
                    else:
                        db[f"movie_{movie_name}"] = movie_data_for_db
                except Exception as e:
                    logger.error(f"Error updating database: {e}")
        else:
            # Send new message with poster
            try:
                # First, try to get poster if not already fetched
                poster_data = None
                if not movie_data.get('poster_fetched', False):
                    logger.info(f"🎬 Fetching poster for new {'series' if movie_data['tag'] == '#SERIES' else 'movie'}: {movie_name}")

                    # Get year from first file or extract from any file
                    year = None
                    if movie_data['files']:
                        # Try to get year from any file
                        for file_data in movie_data['files']:
                            if file_data.get('year'):
                                year = file_data['year']
                                break

                    # Determine if it's a series or movie
                    is_series = movie_data['tag'] == '#SERIES'
                    
                    logger.info(f"🔍 TMDB search for {'TV series' if is_series else 'movie'}: {movie_name} ({year if year else 'No year'})")

                    # Use TMDB API to search for poster
                    poster_data = await image_search.search_poster(movie_name, year, is_series)

                    if poster_data:
                        logger.info(f"✅ Successfully fetched poster from TMDB for: {movie_name}")
                        # Mark as poster fetched to avoid refetching
                        processor.movie_data[movie_name]['poster_fetched'] = True
                    else:
                        logger.warning(f"⚠️ Could not fetch poster from TMDB for: {movie_name}")


                # Send message with or without poster
                if poster_data:
                    # Send with poster
                    sent_message = await client.send_message(
                        UPDATE_CHANNEL_ID,
                        message_text,
                        file=poster_data,
                        parse_mode='html',
                        link_preview=False
                    )
                    processor.movie_data[movie_name]['is_photo'] = True
                    logger.info(f"📸 Created new post with poster for: {movie_name}")
                else:
                    # Send without poster
                    sent_message = await client.send_message(
                        UPDATE_CHANNEL_ID,
                        message_text,
                        parse_mode='html',
                        link_preview=False
                    )
                    logger.info(f"📝 Created new post without poster for: {movie_name}")

                processor.movie_data[movie_name]['message_id'] = sent_message.id

                # Update database
                try:
                    movie_data_for_db = {
                        'files': processor.movie_data[movie_name]['files'],
                        'qualities': list(processor.movie_data[movie_name]['qualities']),
                        'languages': list(processor.movie_data[movie_name]['languages']),
                        'message_id': processor.movie_data[movie_name]['message_id'],
                        'is_photo': processor.movie_data[movie_name]['is_photo'],
                        'tag': processor.movie_data[movie_name]['tag'],
                        'episodes_by_season': {k: list(v) for k, v in processor.movie_data[movie_name]['episodes_by_season'].items()},
                        'poster_fetched': processor.movie_data[movie_name].get('poster_fetched', False)
                    }
                    db[f"movie_{movie_name}"] = movie_data_for_db
                except Exception as e:
                    logger.error(f"Error updating database: {e}")

            except Exception as e:
                logger.error(f"Error sending message with poster: {e}")
                # Fallback to text-only message
                sent_message = await client.send_message(
                    UPDATE_CHANNEL_ID,
                    message_text,
                    parse_mode='html',
                    link_preview=False
                )
                processor.movie_data[movie_name]['message_id'] = sent_message.id

    except Exception as e:
        logger.error(f"Error updating movie post for {movie_name}: {e}")

async def load_existing_data():
    """Load existing movie data from database"""
    try:
        if IS_REPLIT:
            keys = db.keys()
        else:
            keys = list(db.keys())
            
        for key in keys:
            if key.startswith('movie_'):
                movie_name = key.replace('movie_', '', 1)
                data = db[key]

                processor.movie_data[movie_name] = {
                    'files': data.get('files', []),
                    'qualities': set(data.get('qualities', [])),
                    'languages': set(data.get('languages', [])),
                    'message_id': data.get('message_id'),
                    'is_photo': data.get('is_photo', False),
                    'tag': data.get('tag', '#MOVIE'),
                    'episodes_by_season': defaultdict(set, {k: set(v) for k, v in data.get('episodes_by_season', {}).items()}),
                    'poster_fetched': data.get('poster_fetched', False)
                }
        logger.info(f"Loaded {len(processor.movie_data)} movies from database")
    except Exception as e:
        logger.error(f"Error loading existing data: {e}")

async def main():
    """Main function to start the bot"""
    try:
        await client.start(bot_token=BOT_TOKEN)
        logger.info("Bot started successfully!")

        # Load existing data
        await load_existing_data()

        # Start cleanup scheduler (runs immediately to catch expired files from when bot was offline)
        schedule_cleanup()
        logger.info("🧹 Cleanup scheduler started - files will be auto-deleted after 24 hours (real time)")
        logger.info("🚀 Running immediate cleanup to handle files that may have expired while bot was offline")

        # Keep the bot running
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

if __name__ == '__main__':
    asyncio.run(main())
