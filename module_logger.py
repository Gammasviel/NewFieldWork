# .\module_logger.py
import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import datetime

# Your custom formatter is a great feature, so we'll keep it.
class CustomFormatter(logging.Formatter):
    """A custom formatter to add millisecond precision to timestamps."""
    def formatTime(self, record, datefmt=None):
        ct = datetime.datetime.fromtimestamp(record.created)
        if datefmt:
            return ct.strftime(datefmt)
        
        # Format with milliseconds
        s = ct.strftime("%Y-%m-%d %H:%M:%S")
        return f"{s},{int(ct.microsecond / 1000):03d}"

def setup_logging(
    log_level=logging.INFO,
    log_dir="logs",
    log_name="app.log",
    console=True
):
    """
    Sets up the root logger for the entire application.

    This function should be called ONLY ONCE at application startup.

    Args:
        log_level (int): The minimum level of messages to log.
        log_dir (str): The directory to save log files in.
        log_name (str): The name of the log file.
        console (bool): If True, logs will also be output to the console.
    """
    # Get the root logger. All other loggers will inherit from it.
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear any existing handlers to avoid duplicates.
    # This makes the setup function idempotent.
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Create the formatter
    formatter = CustomFormatter(
        "%(asctime)s - %(levelname)-8s - %(name)-20s - %(message)s",
        datefmt=None # Using our custom formatTime
    )

    # 1. Configure Console Handler (if enabled)
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        # You could give the console a different log level if you wanted, e.g., logging.DEBUG
        # console_handler.setLevel(logging.DEBUG)

    # 2. Configure Timed Rotating File Handler
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # This handler rotates the log file at midnight and keeps backups.
    file_handler = TimedRotatingFileHandler(
        filename=log_path / log_name,
        when="midnight",      # Rotate daily
        interval=1,           # Interval is 1 day
        backupCount=7,        # Keep the last 7 days of logs
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logging.info("Logging configured successfully. Outputting to console and file.")