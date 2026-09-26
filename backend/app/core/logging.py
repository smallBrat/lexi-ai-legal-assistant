"""Structured logging for the Lexi AI Legal Assistant backend."""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from app.core.config import get_settings

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "lexi-ai-legal-assistant.log"


def _is_production() -> bool:
    """Detect production environment (Render sets RENDER, or ENVIRONMENT=production)."""
    return bool(os.getenv("RENDER")) or os.getenv("ENVIRONMENT") == "production"


def setup_logger(name: str = "lexi-ai-legal-assistant") -> logging.Logger:
    """Set up a structured logger with the given name.
    
    Args:
        name: Logger name.
        
    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers if already configured
    if logger.handlers:
        return logger
    
    environment = "production" if _is_production() else "development"
    is_production = environment == "production"
    log_level = logging.INFO if not get_settings().is_development() else logging.DEBUG
    logger.setLevel(log_level)
    
    # Console handler with structured format (Render captures stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Structured format: [LEVEL] NAME - MESSAGE (TIMESTAMP)
    formatter = logging.Formatter(
        "[%(levelname)s] %(name)s - %(message)s (%(asctime)s)",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # File logging only in development; never on Render
    file_logging = False
    if not is_production:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        file_logging = True
    
    print(
        "[INFO] Logger initialized\n"
        f"environment={environment}\n"
        f"file_logging={file_logging}"
    )
    
    return logger


# Module-level logger instance
logger = setup_logger()


def info(message: str, **kwargs: Any) -> None:
    """Log an info message with optional context.
    
    Args:
        message: The log message.
        **kwargs: Additional context key-value pairs to include in the log.
    """
    logger.info(message, extra={"context": kwargs})


def warning(message: str, **kwargs: Any) -> None:
    """Log a warning message with optional context.
    
    Args:
        message: The log message.
        **kwargs: Additional context key-value pairs to include in the log.
    """
    logger.warning(message, extra={"context": kwargs})


def error(message: str, **kwargs: Any) -> None:
    """Log an error message with optional context.
    
    Args:
        message: The log message.
        **kwargs: Additional context key-value pairs to include in the log.
    """
    logger.error(message, extra={"context": kwargs})


def debug(message: str, **kwargs: Any) -> None:
    """Log a debug message with optional context.
    
    Args:
        message: The log message.
        **kwargs: Additional context key-value pairs to include in the log.
    """
    logger.debug(message, extra={"context": kwargs})