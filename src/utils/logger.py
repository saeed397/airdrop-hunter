"""Centralized logging with loguru."""
import sys
from pathlib import Path
from loguru import logger

# Lazy import to avoid circular dependency at module level
def setup_logger(level: str = "INFO"):
    """Configure loguru logger."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "airdrop_hunter_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
    )
    return logger


log = setup_logger()
