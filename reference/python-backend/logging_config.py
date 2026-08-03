# python-backend/logging_config.py

import logging
import sys

class CleanFormatter(logging.Formatter):
    """Custom formatter for clean, minimal logs"""
    
    # Color codes for terminal output
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        # Add color if terminal supports it
        if sys.stderr.isatty():
            color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            reset = self.COLORS['RESET']
            record.levelname = f"{color}{record.levelname}{reset}"
        
        # Simple format: timestamp | level | message
        return f"{self.formatTime(record, '%H:%M:%S')} | {record.levelname} | {record.getMessage()}"


def setup_logging(level=logging.INFO):
    """
    Configure minimal, clean logging for the application.
    Only shows essential information: connections, messages, and errors.
    """
    # Remove all existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with clean formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CleanFormatter())
    
    # Configure root logger
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # Silence noisy third-party libraries
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.getLogger('socketio').setLevel(logging.ERROR)
    logging.getLogger('engineio').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('httpx').setLevel(logging.ERROR)
    logging.getLogger('httpcore').setLevel(logging.ERROR)
    logging.getLogger('google').setLevel(logging.ERROR)
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)
    logging.getLogger('agno').setLevel(logging.ERROR)
    logging.getLogger('redis').setLevel(logging.ERROR)
    logging.getLogger('celery').setLevel(logging.ERROR)
    
    return root_logger
