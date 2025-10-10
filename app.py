from flask import Flask, render_template, jsonify
import asyncio
import threading
import logging
from datetime import datetime
import os
import signal
import sys

# Import with fallback handling
try:
    from main import client, processor, BOT_USERNAME
except ImportError as e:
    print(f"Import error: {e}")
    # Create fallbacks if main import fails
    client = None
    processor = None
    BOT_USERNAME = "Movie_Bot"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PID file to track running instance
PID_FILE = 'bot.pid'

def terminate_old_instance():
    """Terminate any old running instance of the bot"""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())

            try:
                # Check if process exists
                os.kill(old_pid, 0)
                logger.info(f"🔪 Found old instance with PID {old_pid}, terminating...")

                # Try graceful termination first
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(2)

                # Check if still running
                try:
                    os.kill(old_pid, 0)
                    # Still running, force kill
                    logger.warning(f"⚠️ Old instance didn't stop gracefully, forcing kill...")
                    os.kill(old_pid, signal.SIGKILL)
                    time.sleep(1)
                    logger.info(f"✅ Successfully terminated old instance (PID {old_pid})")
                except ProcessLookupError:
                    logger.info(f"✅ Old instance terminated gracefully (PID {old_pid})")

            except ProcessLookupError:
                logger.info(f"ℹ️ Old PID {old_pid} not running, cleaning up PID file")
            except PermissionError:
                logger.warning(f"⚠️ No permission to kill PID {old_pid}")

            # Remove old PID file
            os.remove(PID_FILE)
            logger.info(f"🧹 Cleaned up old PID file")

    except Exception as e:
        logger.error(f"❌ Error terminating old instance: {e}")

def write_pid_file():
    """Write current process PID to file"""
    try:
        current_pid = os.getpid()
        with open(PID_FILE, 'w') as f:
            f.write(str(current_pid))
        logger.info(f"📝 Written PID file: {current_pid}")
    except Exception as e:
        logger.error(f"❌ Error writing PID file: {e}")

def cleanup_pid_file(signum=None, frame=None):
    """Clean up PID file on shutdown"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info(f"🧹 Cleaned up PID file on shutdown")
    except Exception as e:
        logger.error(f"❌ Error cleaning up PID file: {e}")

    # Exit gracefully
    sys.exit(0)

# Register cleanup handlers (only in main thread)
try:
    signal.signal(signal.SIGTERM, cleanup_pid_file)
    signal.signal(signal.SIGINT, cleanup_pid_file)
except ValueError:
    # Running in non-main thread or environment that doesn't support signals
    logger.warning("⚠️ Cannot register signal handlers (not in main thread)")

# Global variable to track bot status
bot_status = {"running": False, "last_update": None}

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html', 
                         bot_username=BOT_USERNAME,
                         status=bot_status)

@app.route('/health')
def health_check():
    """Lightweight health check endpoint for monitoring"""
    from flask import request
    
    # Get request information
    user_agent = request.headers.get('User-Agent', 'Unknown')
    remote_addr = request.remote_addr
    full_url = request.url
    host = request.host
    
    # Determine the monitoring service source
    source = "Unknown Monitor"
    if "uptimerobot" in user_agent.lower():
        source = "🟢 UptimeRobot"
    elif "cron-job.org" in user_agent.lower() or "cron" in user_agent.lower():
        source = "🔵 Cron-Job.org"
    elif "bot" in user_agent.lower() or "monitor" in user_agent.lower():
        source = "🤖 Bot Monitor"
    elif "curl" in user_agent.lower():
        source = "💻 Manual Check"
    
    # Log with both website name and monitoring service
    logger.info(f"🏓 Health ping | Service: {source} | Website: {full_url} | IP: {remote_addr}")
    
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()}), 200

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
    try:
        # Terminate any old running instance
        logger.info("🔍 Checking for old instances...")
        terminate_old_instance()

        # Write current PID
        write_pid_file()

        # Start the Telegram bot in background
        start_bot_thread()

        # Start Flask web server
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port, debug=False)

    except KeyboardInterrupt:
        logger.info("🛑 Received keyboard interrupt, shutting down...")
        cleanup_pid_file()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        cleanup_pid_file()
    finally:
        cleanup_pid_file()
