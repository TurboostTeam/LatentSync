from datetime import datetime
from diffusers.utils import logging as diff_logging
import os
import sys


_initialized_loggers = set()


def setup_diffusers_logger(
    logger_name=None,
    log_file=None,
    to_console=True,
    to_file=True,
    level="info"
):
    logger = diff_logging.get_logger(logger_name) if logger_name else diff_logging.get_logger()

    if logger_name in _initialized_loggers:
        return logger

    # Silent mode check
    if not to_console and not to_file:
        print("[Diffusers Logger] All logging outputs are disabled (to_console=False, to_file=False)")
        return logger

    level_map = {
        "debug": diff_logging.logging.DEBUG,
        "info": diff_logging.logging.INFO,
        "warning": diff_logging.logging.WARNING,
        "error": diff_logging.logging.ERROR
    }
    level_value = level_map.get(level.lower(), diff_logging.logging.INFO)
    logger.setLevel(level_value)
    
    # Prevent propagation to parent loggers to avoid unwanted console output
    logger.propagate = False

    formatter = diff_logging.logging.Formatter(
        fmt="[ %(asctime)s ] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if to_console:
        console_handler = diff_logging.logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if to_file:
        if not log_file:
            now = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = f"logs/latentsync_{now}.log"
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        file_handler = diff_logging.logging.FileHandler(
            log_file, mode="a", encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _initialized_loggers.add(logger_name)
    return logger


