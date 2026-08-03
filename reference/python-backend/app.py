# python-backend/app.py

# CRITICAL: Monkey-patch must happen BEFORE any other imports so that redis-py,
# python-socketio, and all other libraries use eventlet's cooperative sockets.
import os
os.environ.setdefault("EVENTLET_NO_GREENDNS", "yes")

import eventlet
eventlet.monkey_patch()

import sys
import logging
from factory import create_app
from extensions import socketio
from logging_config import setup_logging

# Configure clean, professional logging
setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("🚀 Starting Aetheria AI Backend Application")
logger.info("📱 Environment: PROD (Docker)")
logger.info("----------------------------------------------------------------")


# Create the application instance using the factory
app = create_app()

# This block is for local development and debugging.
if __name__ == "__main__":
    # Use socketio.run to correctly handle both Flask and SocketIO requests
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8765)),
        debug=os.environ.get("DEBUG", "False").lower() == "true",
        use_reloader=os.environ.get("DEBUG", "False").lower() == "true"
    )
