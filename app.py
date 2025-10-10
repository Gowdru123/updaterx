from flask import Flask, render_template, jsonify
import asyncio
import threading
import logging
from datetime import datetime
import os
import signal
import sys
import time
import requests
from threading import Timer

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
bot_status = {"running": False, "last_update": None, "last_request_time": time.time()}

# Auto-ping configuration
PING_INTERVAL = 60  # Check every 60 seconds
IDLE_THRESHOLD = 50  # Ping if no activity for 50 seconds
AUTO_PING_ENABLED = True

class AutoPinger:
    def __init__(self):
        self.timer = None
        self.running = False
        
    def start(self):
        """Start auto-ping system"""
        if not self.running:
            self.running = True
            self._schedule_ping()
            logger.info("🔔 Auto-ping system started - will prevent sleep on inactivity")
    
    def stop(self):
        """Stop auto-ping system"""
        self.running = False
        if self.timer:
            self.timer.cancel()
    
    def _schedule_ping(self):
        """Schedule next ping check"""
        if self.running:
            self.timer = Timer(PING_INTERVAL, self._check_and_ping)
            self.timer.daemon = True
            self.timer.start()
    
    def _check_and_ping(self):
        """Check if idle and ping if needed"""
        try:
            current_time = time.time()
            time_since_last_request = current_time - bot_status["last_request_time"]
            
            # If idle for more than threshold, ping self
            if time_since_last_request > IDLE_THRESHOLD:
                logger.info(f"⏰ Idle for {int(time_since_last_request)}s - Auto-pinging to prevent sleep...")
                try:
                    port = int(os.environ.get('PORT', 10000))
                    # Try localhost first, then 0.0.0.0
                    for host in ['127.0.0.1', '0.0.0.0']:
                        try:
                            response = requests.get(f'http://{host}:{port}/health', timeout=5)
                            if response.status_code == 200:
                                logger.info(f"✅ Auto-ping successful - keeping alive")
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"⚠️ Auto-ping failed: {e}")
            else:
                logger.info(f"✨ Active - last request {int(time_since_last_request)}s ago (no ping needed)")
                
        except Exception as e:
            logger.error(f"❌ Error in auto-ping check: {e}")
        finally:
            # Schedule next check
            self._schedule_ping()

auto_pinger = AutoPinger()

@app.route('/')
def index():
    """Main dashboard page"""
    # Update last request time
    bot_status["last_request_time"] = time.time()
    return render_template('index.html', 
                         bot_username=BOT_USERNAME,
                         status=bot_status)

@app.route('/health')
def health_check():
    """Lightweight health check endpoint for monitoring"""
    from flask import request
    
    # Update last request time
    bot_status["last_request_time"] = time.time()
    
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
    elif "python-requests" in user_agent.lower():
        source = "🔔 Auto-Ping"
    
    # Log with both website name and monitoring service
    logger.info(f"🏓 Health ping | Service: {source} | Website: {full_url} | IP: {remote_addr}")
    
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()}), 200

@app.route('/api/status')
def api_status():
    """API endpoint for bot status"""
    bot_status["last_request_time"] = time.time()
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
    bot_status["last_request_time"] = time.time()
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

        # Start auto-pinger to prevent sleep
        if AUTO_PING_ENABLED:
            auto_pinger.start()

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
