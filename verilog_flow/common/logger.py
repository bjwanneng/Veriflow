"""Logging utilities for VeriFlow."""

import logging
import sys
from pathlib import Path
from datetime import datetime


def get_logger(name: str, log_file: Path = None, level=logging.INFO) -> logging.Logger:
    """Get a configured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


class StageLogger:
    """Context manager for logging stage execution."""

    def __init__(self, logger: logging.Logger, stage_name: str):
        self.logger = logger
        self.stage_name = stage_name
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"=== Starting Stage: {self.stage_name} ===")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        if exc_type:
            self.logger.error(f"Stage {self.stage_name} failed after {duration:.2f}s: {exc_val}")
        else:
            self.logger.info(f"Stage {self.stage_name} completed in {duration:.2f}s")
        return False