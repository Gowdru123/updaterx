
from flask import Flask, render_template, jsonify
import asyncio
import threading
import logging
from datetime import datetime
import os
from main import client, processor, BOT_USERNAME

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable to track bot status
bot_status = {"running": False, "last_update": None}

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html', 
                         bot_username=BOT_USERNAME,
                         status=bot_status)

@app.route('/api/status')
def api_status():
    """API endpoint for bot status"""
    movie_count = len(processor.movie_data)
    total_files = sum(len(data['files']) for data in processor.movie_data.values())
    
    return jsonify({
        "bot_running": bot_status["running"],
        "last_update": bot_status["last_update"],
        "total_movies": movie_count,
        "total_files": total_files,
        "bot_username": BOT_USERNAME
    })

@app.route('/api/movies')
def api_movies():
    """API endpoint for movie list"""
    movies = []
    for movie_name, data in processor.movie_data.items():
        movies.append({
            "name": movie_name,
            "tag": data.get('tag', '#MOVIE'),
            "file_count": len(data['files']),
            "qualities": list(data.get('qualities', [])),
            "languages": list(data.get('languages', []))
        })
    
    return jsonify(movies)

def run_bot():
    """Run the Telegram bot in a separate thread"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def start_bot():
            global bot_status
            from main import main
            bot_status["running"] = True
            bot_status["last_update"] = datetime.now().isoformat()
            await main()
        
        loop.run_until_complete(start_bot())
    except Exception as e:
        logger.error(f"Bot error: {e}")
        bot_status["running"] = False

def start_bot_thread():
    """Start bot in background thread"""
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("🤖 Telegram bot started in background thread")

if __name__ == '__main__':
    # Start the Telegram bot in background
    start_bot_thread()
    
    # Start Flask web server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
