"""Structured logger factory used across all argus modules."""
import logging
import os
import sys


def get_logger(name: str) -> logging.Logger:
    """Return a logger with an ISO-8601 timestamp formatter.

    Handlers are added only once, so calling this multiple times with the same
    name is safe and idempotent.  Log level is read from the ``LOG_LEVEL``
    environment variable (default: ``INFO``).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    return logger
