"""Structured logging for the Lexi AI Legal Assistant backend."""

import logging
import sys
from typing import Any

from app.core.config import get_settings


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
    
    log_level = logging.INFO if not get_settings().is_development() else logging.DEBUG
    logger.setLevel(log_level)
    
    # Console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Structured format: [LEVEL] NAME - MESSAGE (TIMESTAMP)
    formatter = logging.Formatter(
        "[%(levelname)s] %(name)s - %(message)s (%(asctime)s)",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Also log to file in production
    if get_settings().is_production():
        file_handler = logging.FileHandler("logs/lexi-ai-legal-assistant.log")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
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