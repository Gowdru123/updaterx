
import os

class Config:
    # Telegram API credentials
    API_ID = os.getenv('API_ID')
    API_HASH = os.getenv('API_HASH')
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # Channel IDs
    DB_CHANNEL_ID = int(os.getenv('DB_CHANNEL_ID', '-1003079659341'))
    UPDATE_CHANNEL_ID = int(os.getenv('UPDATE_CHANNEL_ID', '-1002871457605'))
    
    # Bot username
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'JNK_Autofilter_Bot')
    
    # File processing settings
    SUPPORTED_FORMATS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm']
    
    # Quality patterns
    QUALITY_PATTERNS = [
        '720p', '1080p', '480p', '360p', '4K', '2K', 'HD', 'CAM', 
        'HDRip', 'DVDRip', 'BluRay', 'WEBRip', 'HDCAM', 'HDTC', '260p'
    ]
    
    # Language patterns
    LANGUAGE_PATTERNS = [
        'Hindi', 'English', 'Tamil', 'Telugu', 'Malayalam', 'Kannada',
        'Bengali', 'Marathi', 'Gujarati', 'Punjabi', 'Urdu', 'Bhojpuri'
    ]
    
    # Message Templates
    MOVIE_TEMPLATE = """🎬 Title : <code>{title}</code>
📅 ʏᴇᴀʀ : <b>{year}</b>
🔊 ᴀᴜᴅɪᴏ : <b>{language}</b>
📤 ǫᴜᴀʟɪᴛʏ : <b>HD</b>

📁 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : <b>{total_files}</b>"""

    SERIES_TEMPLATE = """🎬 ᴛɪᴛʟᴇ : <code>{title}</code>
📅 ʏᴇᴀʀ : <b>{year}</b>
🔊 ᴀᴜᴅɪᴏ : <b>{language}</b>
📤 ǫᴜᴀʟɪᴛʏ : <b>HD</b>
📺 ᴇᴘɪꜱᴏᴅᴇꜱ : <b>{episodes}</b>

📁 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : <b>{total_files}</b>"""
