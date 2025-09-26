
from typing import Dict, List
import re

class MessageFormatter:
    def __init__(self, bot_username: str):
        self.bot_username = bot_username
    
    def format_movie_update(self, movie_name: str, movie_data: Dict) -> str:
        """Format the movie update message for the channel"""
        files = movie_data.get('files', [])
        qualities = sorted(list(set(movie_data.get('qualities', ['Unknown']))))
        languages = sorted(list(set(movie_data.get('languages', ['Unknown']))))
        tag = movie_data.get('tag', '#MOVIE')
        
        # Extract file sizes from files and keep unique ones in order
        file_sizes = []
        seen_sizes = set()
        for file_info in files:
            if isinstance(file_info, dict) and file_info.get('file_size') and file_info['file_size'] != 'N/A':
                size = file_info['file_size']
                if size not in seen_sizes:
                    file_sizes.append(size)
                    seen_sizes.add(size)
        
        # Create header
        message = f"🎬 **{movie_name}**\n"
        message += "=" * 30 + "\n\n"
        
        # Movie/Series details
        message += f"📁 **Total Files:** {len(files)}\n"
        message += f"🎯 **Available Quality:** {' | '.join(qualities)}\n"
        message += f"🌍 **Language:** {' | '.join(languages)}\n"
        if file_sizes:
            message += f"📊 **File Sizes:** {' | '.join(file_sizes)}\n"
        else:
            message += f"📊 **File Sizes:** N/A\n"
        
        # Add episode information for series
        if tag == "#SERIES":
            episodes_by_season = movie_data.get('episodes_by_season', {})
            if episodes_by_season:
                message += f"📺 **Episodes:**\n"
                for season, episodes in sorted(episodes_by_season.items(), key=lambda x: int(x[0])):
                    if isinstance(episodes, set):
                        episode_list = sorted(episodes, key=lambda x: int(x.split('-')[0]) if '-' in x else int(x))
                    else:
                        episode_list = sorted(episodes, key=lambda x: int(x.split('-')[0]) if '-' in x else int(x))
                    message += f"Season {season}: {', '.join(episode_list)}\n"
        
        message += "\n"
        
        # File list (if reasonable number and not series)
        if len(files) <= 5 and tag != "#SERIES":
            message += "📋 **Files:**\n"
            for i, file_info in enumerate(files, 1):
                filename = file_info.get('filename', 'Unknown')
                file_size = file_info.get('file_size', 'N/A')
                # Truncate long filenames
                display_name = filename[:40] + "..." if len(filename) > 40 else filename
                message += f"{i}. `{display_name}` ({file_size})\n"
            message += "\n"
        
        # Download link
        download_link = self.generate_download_link(movie_name)
        message += f"📥 **Download All Files:**\n[🔗 Click Here to Download]({download_link})\n\n"
        
        # Hashtags for better discoverability
        hashtags = self.generate_hashtags(movie_name, languages, qualities)
        message += f"**Tags:** {hashtags}\n\n"
        
        # Footer
        message += "⚡ **Auto-Updated by Bot** ⚡"
        
        return message
    
    def generate_download_link(self, movie_name: str) -> str:
        """Generate download link for the bot"""
        # Clean movie name for URL
        clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', movie_name)
        clean_name = re.sub(r'\s+', '-', clean_name.strip())
        return f"https://t.me/{self.bot_username}?start=getfile---{clean_name}"
    
    def generate_hashtags(self, movie_name: str, languages: List[str], qualities: List[str]) -> str:
        """Generate relevant hashtags"""
        tags = []
        
        # Movie name tag
        movie_tag = re.sub(r'[^a-zA-Z0-9]', '', movie_name.replace(' ', '_'))
        if movie_tag:
            tags.append(f"#{movie_tag}")
        
        # Language tags
        for lang in languages:
            if lang != 'Unknown':
                tags.append(f"#{lang}")
        
        # Quality tags
        for quality in qualities:
            if quality != 'Unknown':
                clean_quality = re.sub(r'[^a-zA-Z0-9]', '', quality)
                tags.append(f"#{clean_quality}")
        
        # General tags
        tags.extend(["#Movie", "#Download", "#Latest"])
        
        return ' '.join(tags[:10])  # Limit to 10 tags
    
    def format_file_info(self, file_data: Dict) -> str:
        """Format individual file information"""
        filename = file_data.get('filename', 'Unknown')
        file_size = file_data.get('file_size', 'Unknown')
        quality = file_data.get('quality', 'Unknown')
        
        info = f"📄 **File:** `{filename}`\n"
        if file_size != 'Unknown' and file_size != 'N/A':
            info += f"📊 **Size:** {file_size}\n"
        if quality != 'Unknown' and quality != 'N/A':
            info += f"🎯 **Quality:** {quality}\n"
        
        return info
